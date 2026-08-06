from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.contrib.auth.models import User as DjangoUser
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import TeamRole
from apps.operations.commands import CHECKPOINT_COMMAND_TYPE
from apps.operations.contracts import (
    CheckpointPayloadV1,
    CreateCheckpointCommandV1,
    TaskEnvelopeV2,
)
from apps.operations.models import (
    ActorType,
    AuditEvent,
    OutboxStatus,
    PipelineRun,
    PipelineStatus,
    PipelineStepRun,
    PipelineTrigger,
    StepStatus,
    TaskOutbox,
)


class InvalidOutboxTransition(ValueError):
    pass


@dataclass(frozen=True)
class CheckpointCreationResult:
    pipeline_run: PipelineRun
    outbox: TaskOutbox
    created: bool


def _actor_role_id(user: DjangoUser | None) -> UUID | None:
    if user is None:
        return None
    return TeamRole.objects.filter(user=user).values_list("pk", flat=True).first()


@transaction.atomic
def create_checkpoint_command(
    *,
    command: CreateCheckpointCommandV1,
    actor: DjangoUser | None,
) -> CheckpointCreationResult:
    now = timezone.now()
    pipeline_run, created = PipelineRun.objects.get_or_create(
        idempotency_key=command.idempotency_key,
        defaults={
            "pipeline_name": "operations.checkpoint",
            "stage": "checkpoint_queued",
            "status": PipelineStatus.QUEUED,
            "trigger": PipelineTrigger.MANUAL,
            "requested_by": actor,
            "request_id": command.request_id,
            "heartbeat_at": now,
            "input_count": 1,
            "policy_versions": {"operations": "2.1", "envelope": "2.1"},
            "context": {"purpose": "outbox_integrity_checkpoint"},
        },
    )
    if not created:
        return CheckpointCreationResult(
            pipeline_run=pipeline_run,
            outbox=pipeline_run.outbox_commands.get(
                idempotency_key=f"{command.idempotency_key}:dispatch"
            ),
            created=False,
        )
    payload = CheckpointPayloadV1(pipeline_run_id=pipeline_run.pk)
    outbox = TaskOutbox(
        command_type=CHECKPOINT_COMMAND_TYPE,
        payload=payload.model_dump(mode="json"),
        payload_schema_version="1.0",
        idempotency_key=f"{command.idempotency_key}:dispatch",
        pipeline_run=pipeline_run,
        request_id=command.request_id,
        available_at=now,
    )
    outbox.full_clean()
    outbox.save()
    AuditEvent.objects.create(
        actor_type=ActorType.USER if actor is not None else ActorType.SYSTEM,
        actor_id=_actor_role_id(actor),
        action="operations.checkpoint_queued",
        object_type="pipeline_run",
        object_id=pipeline_run.pk,
        before_summary={},
        after_summary={"status": PipelineStatus.QUEUED, "outbox_id": str(outbox.pk)},
        reason_key="manual_integrity_checkpoint",
        request_id=command.request_id,
        pipeline_run=pipeline_run,
    )
    return CheckpointCreationResult(pipeline_run=pipeline_run, outbox=outbox, created=True)


@transaction.atomic
def execute_checkpoint_command(envelope: TaskEnvelopeV2) -> bool:
    if envelope.command_type != CHECKPOINT_COMMAND_TYPE:
        raise ValueError("Unsupported checkpoint command type.")
    run = PipelineRun.objects.select_for_update().get(pk=envelope.pipeline_run_id)
    if envelope.object_id != run.pk:
        raise ValueError("Envelope object does not match its pipeline run.")
    outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=run)
    if outbox.idempotency_key != envelope.idempotency_key:
        raise ValueError("Envelope idempotency key does not match its outbox command.")

    effect_key = f"{envelope.idempotency_key}:effect"
    if PipelineStepRun.objects.filter(idempotency_key=effect_key).exists():
        return False

    now = timezone.now()
    PipelineStepRun.objects.create(
        pipeline_run=run,
        stage="checkpoint_completed",
        status=StepStatus.COMPLETE,
        idempotency_key=effect_key,
        started_at=now,
        heartbeat_at=now,
        completed_at=now,
        input_ids={"outbox_id": str(outbox.pk)},
        output_ids={"pipeline_run_id": str(run.pk)},
    )
    before_status = run.status
    run.stage = "checkpoint_complete"
    run.status = PipelineStatus.COMPLETE
    run.completed_at = now
    run.heartbeat_at = now
    run.output_count = 1
    run.attempts += 1
    run.row_version += 1
    run.save(
        update_fields=(
            "stage",
            "status",
            "completed_at",
            "heartbeat_at",
            "output_count",
            "attempts",
            "row_version",
            "updated_at",
        )
    )
    AuditEvent.objects.create(
        actor_type=ActorType.SYSTEM,
        action="operations.checkpoint_completed",
        object_type="pipeline_run",
        object_id=run.pk,
        before_summary={"status": before_status},
        after_summary={"status": PipelineStatus.COMPLETE, "row_version": run.row_version},
        reason_key="idempotent_command_consumed",
        request_id=run.request_id,
        pipeline_run=run,
    )
    return True


@transaction.atomic
def retry_outbox_command(
    *,
    outbox_id: UUID,
    actor: DjangoUser,
    request_id: UUID | None,
    reason: str,
) -> TaskOutbox:
    outbox = TaskOutbox.objects.select_for_update().get(pk=outbox_id)
    if outbox.status != OutboxStatus.FAILED:
        raise InvalidOutboxTransition("Only failed outbox commands can be retried.")
    before = {"status": outbox.status, "attempts": outbox.attempts}
    outbox.status = OutboxStatus.PENDING
    outbox.available_at = timezone.now()
    outbox.claimed_by = ""
    outbox.claimed_at = None
    outbox.save(update_fields=("status", "available_at", "claimed_by", "claimed_at"))
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        actor_id=_actor_role_id(actor),
        action="operations.outbox_retry_requested",
        object_type="task_outbox",
        object_id=outbox.pk,
        before_summary=before,
        after_summary={"status": OutboxStatus.PENDING, "attempts": outbox.attempts},
        reason_key=reason,
        request_id=request_id,
        pipeline_run=outbox.pipeline_run,
    )
    return outbox
