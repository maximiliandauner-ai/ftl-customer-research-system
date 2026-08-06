from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.utils import timezone

from apps.operations.contracts import CreateCheckpointCommandV1
from apps.operations.models import (
    AuditEvent,
    OutboxStatus,
    PipelineRun,
    PipelineStatus,
    PipelineStepRun,
    TaskOutbox,
)
from apps.operations.outbox import (
    MAX_AUTOMATIC_ATTEMPTS,
    PublishedMessage,
    build_envelope,
    claim_outbox_batch,
    dispatch_outbox_batch,
    recover_stale_claims,
)
from apps.operations.services import (
    InvalidOutboxTransition,
    create_checkpoint_command,
    execute_checkpoint_command,
    retry_outbox_command,
)


class SuccessfulPublisher:
    def __init__(self) -> None:
        self.envelopes = []

    def publish(self, envelope):  # type: ignore[no-untyped-def]
        self.envelopes.append(envelope)
        return PublishedMessage(message_id="broker-message-1")


class FailedPublisher:
    def publish(self, _envelope):  # type: ignore[no-untyped-def]
        raise ConnectionError("password=broker-secret connection refused")


def checkpoint(user: User, key: str = "operations.checkpoint:test-0001"):
    return create_checkpoint_command(
        command=CreateCheckpointCommandV1(idempotency_key=key, request_id=uuid4()),
        actor=user,
    )


@pytest.mark.django_db
def test_checkpoint_transaction_is_atomic_idempotent_and_correlated() -> None:
    user = User.objects.create_user(username="researcher")

    first = checkpoint(user)
    second = checkpoint(user)

    assert first.created is True
    assert second.created is False
    assert first.pipeline_run.pk == second.pipeline_run.pk
    assert first.outbox.pk == second.outbox.pk
    assert PipelineRun.objects.count() == 1
    assert TaskOutbox.objects.count() == 1
    event = AuditEvent.objects.get(action="operations.checkpoint_queued")
    assert event.request_id == first.pipeline_run.request_id == first.outbox.request_id
    assert first.outbox.payload == {"pipeline_run_id": str(first.pipeline_run.pk)}


@pytest.mark.django_db(transaction=True)
def test_checkpoint_rolls_back_domain_and_outbox_when_audit_fails() -> None:
    user = User.objects.create_user(username="rollback")

    with (
        patch.object(AuditEvent.objects, "create", side_effect=DatabaseError("audit unavailable")),
        pytest.raises(DatabaseError),
    ):
        checkpoint(user, "operations.checkpoint:rollback")

    assert PipelineRun.objects.count() == 0
    assert TaskOutbox.objects.count() == 0


@pytest.mark.django_db
def test_successful_dispatch_records_broker_identity() -> None:
    user = User.objects.create_user(username="publisher")
    created = checkpoint(user)
    publisher = SuccessfulPublisher()

    published = dispatch_outbox_batch(publisher=publisher, worker_id="dispatcher-a")
    created.outbox.refresh_from_db()

    assert published == 1
    assert created.outbox.status == OutboxStatus.PUBLISHED
    assert created.outbox.attempts == 1
    assert created.outbox.broker_message_id == "broker-message-1"
    assert publisher.envelopes[0].outbox_id == created.outbox.pk


@pytest.mark.django_db
def test_broker_failure_preserves_command_and_recovery_publishes_later() -> None:
    user = User.objects.create_user(username="resilience")
    created = checkpoint(user)

    assert dispatch_outbox_batch(publisher=FailedPublisher(), worker_id="dispatcher-a") == 0
    created.outbox.refresh_from_db()
    assert created.outbox.status == OutboxStatus.FAILED
    assert created.outbox.attempts == 1
    assert created.outbox.last_error_code == "OUTBOX_PUBLISH_FAILED"
    assert "broker-secret" not in created.outbox.last_error_message
    assert PipelineRun.objects.filter(pk=created.pipeline_run.pk).exists()

    TaskOutbox.objects.filter(pk=created.outbox.pk).update(available_at=timezone.now())
    assert dispatch_outbox_batch(publisher=SuccessfulPublisher(), worker_id="dispatcher-b") == 1
    created.outbox.refresh_from_db()
    assert created.outbox.status == OutboxStatus.PUBLISHED
    assert created.outbox.attempts == 2


@pytest.mark.django_db
def test_duplicate_delivery_produces_one_domain_effect_and_completion_audit() -> None:
    user = User.objects.create_user(username="consumer")
    created = checkpoint(user)
    envelope = build_envelope(created.outbox)

    assert execute_checkpoint_command(envelope) is True
    assert execute_checkpoint_command(envelope) is False
    created.pipeline_run.refresh_from_db()

    assert created.pipeline_run.status == PipelineStatus.COMPLETE
    assert created.pipeline_run.output_count == 1
    assert PipelineStepRun.objects.filter(pipeline_run=created.pipeline_run).count() == 1
    assert AuditEvent.objects.filter(action="operations.checkpoint_completed").count() == 1


@pytest.mark.django_db
def test_stale_claim_recovery_returns_command_to_pending_and_audits() -> None:
    user = User.objects.create_user(username="recovery")
    created = checkpoint(user)
    claim_outbox_batch(worker_id="lost-worker")
    TaskOutbox.objects.filter(pk=created.outbox.pk).update(
        claimed_at=timezone.now() - timedelta(minutes=10)
    )

    assert recover_stale_claims() == 1
    created.outbox.refresh_from_db()
    assert created.outbox.status == OutboxStatus.PENDING
    assert created.outbox.last_error_code == "TASK_STALE"
    assert created.outbox.claimed_by == ""
    assert AuditEvent.objects.filter(action="operations.outbox_claim_recovered").count() == 1


@pytest.mark.django_db
def test_exhausted_failed_command_requires_manual_retry() -> None:
    user = User.objects.create_user(username="founder")
    created = checkpoint(user)
    TaskOutbox.objects.filter(pk=created.outbox.pk).update(
        status=OutboxStatus.FAILED,
        attempts=MAX_AUTOMATIC_ATTEMPTS,
        available_at=timezone.now(),
    )

    assert claim_outbox_batch(worker_id="automatic") == ()
    retried = retry_outbox_command(
        outbox_id=created.outbox.pk,
        actor=user,
        request_id=uuid4(),
        reason="manual_operational_retry",
    )
    assert retried.status == OutboxStatus.PENDING
    assert claim_outbox_batch(worker_id="manual") == (created.outbox.pk,)


@pytest.mark.django_db
def test_retry_rejects_non_failed_state() -> None:
    user = User.objects.create_user(username="retry-guard")
    created = checkpoint(user)

    with pytest.raises(InvalidOutboxTransition, match="Only failed"):
        retry_outbox_command(
            outbox_id=created.outbox.pk,
            actor=user,
            request_id=uuid4(),
            reason="unsafe_retry",
        )


@pytest.mark.django_db
def test_unknown_command_fails_permanently_without_publication() -> None:
    user = User.objects.create_user(username="unknown-route")
    created = checkpoint(user)
    TaskOutbox.objects.filter(pk=created.outbox.pk).update(command_type="unknown.command")

    assert dispatch_outbox_batch(publisher=SuccessfulPublisher(), worker_id="dispatcher-a") == 0
    created.outbox.refresh_from_db()
    assert created.outbox.status == OutboxStatus.FAILED
    assert created.outbox.attempts == MAX_AUTOMATIC_ATTEMPTS
    assert created.outbox.last_error_code == "OUTBOX_COMMAND_UNSUPPORTED"


@pytest.mark.django_db
def test_outbox_rejects_non_object_and_large_payloads() -> None:
    user = User.objects.create_user(username="payload")
    created = checkpoint(user)
    created.outbox.payload = ["not", "an", "object"]
    with pytest.raises(ValidationError, match="JSON object"):
        created.outbox.full_clean()
    created.outbox.payload = {"body": "x" * 9_000}
    with pytest.raises(ValidationError, match="8 KiB"):
        created.outbox.full_clean()


@pytest.mark.django_db
def test_audit_records_reject_application_mutation_and_deletion() -> None:
    user = User.objects.create_user(username="auditor")
    event = AuditEvent.objects.get(pk=checkpoint(user).pipeline_run.audit_events.get().pk)
    event.reason_key = "rewritten"

    with pytest.raises(TypeError, match="append-only"):
        event.save()
    with pytest.raises(TypeError, match="append-only"):
        event.delete()
    with pytest.raises(TypeError, match="append-only"):
        AuditEvent.objects.filter(pk=event.pk).update(reason_key="rewritten")
