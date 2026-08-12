from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.logging import redact
from apps.operations.commands import (
    ASSET_MATCH_COMMAND_TYPE,
    BUYER_ROLES_INFER_COMMAND_TYPE,
    CHECKPOINT_COMMAND_TYPE,
    COMPANIES_AGGREGATE_COMMAND_TYPE,
    COMPANY_PROFILE_ENRICH_COMMAND_TYPE,
    CONTACT_SOURCE_SCAN_COMMAND_TYPE,
    DISCOVERY_EXECUTE_COMMAND_TYPE,
    JOBS_PARSE_COMMAND_TYPE,
    RESEARCH_EXTRACT_COMMAND_TYPE,
    RESEARCH_PUBLIC_COMMAND_TYPE,
    SIGNALS_CLASSIFY_COMMAND_TYPE,
    SIGNALS_DETECT_COMMAND_TYPE,
    SOLUTION_DESIGN_COMMAND_TYPE,
    SOURCE_FETCH_COMMAND_TYPE,
)
from apps.operations.contracts import (
    CheckpointPayloadV1,
    TargetCommandPayloadV1,
    TaskEnvelopeV2,
)
from apps.operations.models import ActorType, AuditEvent, OutboxStatus, TaskOutbox
from config.celery import app as celery_app

MAX_AUTOMATIC_ATTEMPTS = 8
MAX_BATCH_SIZE = 100
STALE_CLAIM_AFTER = timedelta(minutes=5)


class UnsupportedCommand(ValueError):
    pass


@dataclass(frozen=True)
class CommandRoute:
    task_name: str
    queue: str


@dataclass(frozen=True)
class PublishedMessage:
    message_id: str


class Publisher(Protocol):
    def publish(self, envelope: TaskEnvelopeV2) -> PublishedMessage: ...


COMMAND_ROUTES = {
    CHECKPOINT_COMMAND_TYPE: CommandRoute(
        task_name="operations.complete_checkpoint",
        queue="maintenance",
    ),
    SOURCE_FETCH_COMMAND_TYPE: CommandRoute(
        task_name="sources.fetch_public_source",
        queue="fetch",
    ),
    COMPANY_PROFILE_ENRICH_COMMAND_TYPE: CommandRoute(
        task_name="companies.enrich_profile",
        queue="fetch",
    ),
    JOBS_PARSE_COMMAND_TYPE: CommandRoute(
        task_name="jobs.parse_source_snapshot",
        queue="parse",
    ),
    DISCOVERY_EXECUTE_COMMAND_TYPE: CommandRoute(
        task_name="discovery.execute",
        queue="discovery",
    ),
    SIGNALS_DETECT_COMMAND_TYPE: CommandRoute(
        task_name="signals.detect_posting_change",
        queue="classification",
    ),
    SIGNALS_CLASSIFY_COMMAND_TYPE: CommandRoute(
        task_name="signals.classify_signal",
        queue="classification",
    ),
    COMPANIES_AGGREGATE_COMMAND_TYPE: CommandRoute(
        task_name="opportunities.aggregate_company",
        queue="aggregation",
    ),
    RESEARCH_PUBLIC_COMMAND_TYPE: CommandRoute(
        task_name="research.run_public",
        queue="research",
    ),
    RESEARCH_EXTRACT_COMMAND_TYPE: CommandRoute(
        task_name="research.extract",
        queue="research",
    ),
    SOLUTION_DESIGN_COMMAND_TYPE: CommandRoute(
        task_name="solutions.design",
        queue="solution_design",
    ),
    ASSET_MATCH_COMMAND_TYPE: CommandRoute(
        task_name="solutions.match_assets",
        queue="asset_matching",
    ),
    BUYER_ROLES_INFER_COMMAND_TYPE: CommandRoute(
        task_name="contacts.infer_roles",
        queue="contact_enrichment",
    ),
    CONTACT_SOURCE_SCAN_COMMAND_TYPE: CommandRoute(
        task_name="contacts.scan_source",
        queue="contact_enrichment",
    ),
}


class CeleryPublisher:
    def publish(self, envelope: TaskEnvelopeV2) -> PublishedMessage:
        route = COMMAND_ROUTES.get(envelope.command_type)
        if route is None:
            raise UnsupportedCommand("The command type has no active task route.")
        result = celery_app.send_task(
            route.task_name,
            args=[envelope.model_dump(mode="json")],
            queue=route.queue,
            headers={
                "request_id": str(envelope.request_id or envelope.outbox_id),
                "pipeline_run_id": str(envelope.pipeline_run_id),
                "outbox_id": str(envelope.outbox_id),
            },
        )
        return PublishedMessage(message_id=str(result.id))


def _safe_error(exc: Exception) -> str:
    message = redact(str(exc)).replace("\n", " ").strip()
    return (message or exc.__class__.__name__)[:500]


def _retry_delay(attempt: int) -> timedelta:
    seconds = min(5 * (2 ** max(attempt - 1, 0)), 900)
    return timedelta(seconds=seconds)


def _eligible() -> Q:
    return Q(status=OutboxStatus.PENDING) | Q(
        status=OutboxStatus.FAILED,
        attempts__lt=MAX_AUTOMATIC_ATTEMPTS,
    )


@transaction.atomic
def claim_outbox_batch(*, worker_id: str, limit: int = 100) -> tuple[UUID, ...]:
    bounded_limit = max(1, min(limit, MAX_BATCH_SIZE))
    now = timezone.now()
    queryset = TaskOutbox.objects.filter(_eligible(), available_at__lte=now).order_by("created_at")
    if connection.features.has_select_for_update_skip_locked:
        queryset = queryset.select_for_update(skip_locked=True)
    else:
        queryset = queryset.select_for_update()
    claimed: list[UUID] = []
    for command in queryset[:bounded_limit]:
        command.status = OutboxStatus.PUBLISHING
        command.claimed_by = worker_id[:128]
        command.claimed_at = now
        command.attempts += 1
        command.save(update_fields=("status", "claimed_by", "claimed_at", "attempts"))
        claimed.append(command.pk)
    return tuple(claimed)


def build_envelope(command: TaskOutbox) -> TaskEnvelopeV2:
    if command.command_type not in COMMAND_ROUTES:
        raise UnsupportedCommand("The command type has no active envelope policy.")
    if command.command_type == CHECKPOINT_COMMAND_TYPE:
        checkpoint_payload = CheckpointPayloadV1.model_validate(command.payload)
        payload = TargetCommandPayloadV1(
            pipeline_run_id=checkpoint_payload.pipeline_run_id,
            object_id=checkpoint_payload.pipeline_run_id,
        )
    else:
        payload = TargetCommandPayloadV1.model_validate(command.payload)
    if payload.pipeline_run_id != command.pipeline_run_id:
        raise ValueError("The command payload does not match its canonical pipeline run.")
    requested_by = (
        f"user:{command.pipeline_run.requested_by_id}"
        if command.pipeline_run.requested_by_id is not None
        else "system"
    )
    return TaskEnvelopeV2(
        outbox_id=command.pk,
        pipeline_run_id=command.pipeline_run_id,
        command_type=command.command_type,
        object_id=payload.object_id,
        idempotency_key=command.idempotency_key,
        requested_by=requested_by,
        request_id=command.request_id,
    )


@transaction.atomic
def _mark_published(*, outbox_id: UUID, worker_id: str, message_id: str) -> bool:
    command = TaskOutbox.objects.select_for_update().get(pk=outbox_id)
    if command.status != OutboxStatus.PUBLISHING or command.claimed_by != worker_id:
        return False
    command.status = OutboxStatus.PUBLISHED
    command.published_at = timezone.now()
    command.broker_message_id = message_id[:255]
    command.last_error_code = ""
    command.last_error_message = ""
    command.save(
        update_fields=(
            "status",
            "published_at",
            "broker_message_id",
            "last_error_code",
            "last_error_message",
        )
    )
    return True


@transaction.atomic
def _mark_failed(
    *,
    outbox_id: UUID,
    worker_id: str,
    error_code: str,
    error_message: str,
    retryable: bool,
) -> bool:
    command = TaskOutbox.objects.select_for_update().get(pk=outbox_id)
    if command.status != OutboxStatus.PUBLISHING or command.claimed_by != worker_id:
        return False
    command.status = OutboxStatus.FAILED
    command.available_at = timezone.now() + _retry_delay(command.attempts)
    command.last_error_code = error_code
    command.last_error_message = error_message
    if not retryable:
        command.attempts = max(command.attempts, MAX_AUTOMATIC_ATTEMPTS)
    command.save(
        update_fields=(
            "status",
            "available_at",
            "attempts",
            "last_error_code",
            "last_error_message",
        )
    )
    return True


def dispatch_outbox_batch(
    *,
    publisher: Publisher | None = None,
    worker_id: str | None = None,
    limit: int = 100,
) -> int:
    active_publisher = publisher or CeleryPublisher()
    claim_owner = (worker_id or f"{socket.gethostname()}:{timezone.now().timestamp()}")[:128]
    claimed_ids = claim_outbox_batch(worker_id=claim_owner, limit=limit)
    published = 0
    for outbox_id in claimed_ids:
        command = TaskOutbox.objects.select_related("pipeline_run").get(pk=outbox_id)
        try:
            envelope = build_envelope(command)
            result = active_publisher.publish(envelope)
        except UnsupportedCommand as exc:
            _mark_failed(
                outbox_id=outbox_id,
                worker_id=claim_owner,
                error_code="OUTBOX_COMMAND_UNSUPPORTED",
                error_message=_safe_error(exc),
                retryable=False,
            )
        except Exception as exc:
            _mark_failed(
                outbox_id=outbox_id,
                worker_id=claim_owner,
                error_code="OUTBOX_PUBLISH_FAILED",
                error_message=_safe_error(exc),
                retryable=True,
            )
        else:
            if _mark_published(
                outbox_id=outbox_id,
                worker_id=claim_owner,
                message_id=result.message_id,
            ):
                published += 1
    return published


@transaction.atomic
def recover_stale_claims(*, older_than: timedelta = STALE_CLAIM_AFTER) -> int:
    cutoff = timezone.now() - older_than
    queryset = TaskOutbox.objects.filter(
        status=OutboxStatus.PUBLISHING,
        claimed_at__lt=cutoff,
    ).order_by("claimed_at")
    if connection.features.has_select_for_update_skip_locked:
        queryset = queryset.select_for_update(skip_locked=True)
    else:
        queryset = queryset.select_for_update()
    recovered = 0
    for command in queryset[:MAX_BATCH_SIZE]:
        previous_owner = command.claimed_by
        command.status = OutboxStatus.PENDING
        command.available_at = timezone.now()
        command.claimed_by = ""
        command.claimed_at = None
        command.last_error_code = "TASK_STALE"
        command.last_error_message = "A stale publication claim was recovered."
        command.save(
            update_fields=(
                "status",
                "available_at",
                "claimed_by",
                "claimed_at",
                "last_error_code",
                "last_error_message",
            )
        )
        AuditEvent.objects.create(
            actor_type=ActorType.SYSTEM,
            action="operations.outbox_claim_recovered",
            object_type="task_outbox",
            object_id=command.pk,
            before_summary={"status": OutboxStatus.PUBLISHING, "claimed_by": previous_owner},
            after_summary={"status": OutboxStatus.PENDING},
            reason_key="stale_claim",
            request_id=command.request_id,
            pipeline_run=command.pipeline_run,
        )
        recovered += 1
    return recovered
