from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.utils import timezone

from apps.operations.contracts import CreateCheckpointCommandV1
from apps.operations.models import AuditEvent, OutboxStatus, PipelineStepRun, TaskOutbox
from apps.operations.outbox import build_envelope, claim_outbox_batch, dispatch_outbox_batch
from apps.operations.services import create_checkpoint_command, execute_checkpoint_command


class OfflineBroker:
    def publish(self, _envelope):  # type: ignore[no-untyped-def]
        raise ConnectionError("broker unavailable")


def create_checkpoint(user: User, key: str):
    return create_checkpoint_command(
        command=CreateCheckpointCommandV1(idempotency_key=key, request_id=uuid4()),
        actor=user,
    )


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_audit_trigger_rejects_update_and_delete() -> None:
    assert connection.vendor == "postgresql"
    user = User.objects.create_user(username="trigger-test")
    event = create_checkpoint(user, "operations.checkpoint:trigger").pipeline_run.audit_events.get()

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE operations_auditevent SET reason_key = %s WHERE id = %s",
            ["tampered", event.pk],
        )
    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM operations_auditevent WHERE id = %s", [event.pk])

    event.refresh_from_db()
    assert event.reason_key == "manual_integrity_checkpoint"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_skip_locked_claims_single_command_once_concurrently() -> None:
    user = User.objects.create_user(username="claim-test")
    created = create_checkpoint(user, "operations.checkpoint:concurrent-claim")
    barrier = Barrier(2)

    def claim(worker_id: str):  # type: ignore[no-untyped-def]
        close_old_connections()
        barrier.wait(timeout=5)
        try:
            return claim_outbox_batch(worker_id=worker_id, limit=1)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("worker-a", "worker-b")))

    flattened = [identifier for batch in results for identifier in batch]
    assert flattened == [created.outbox.pk]
    created.outbox.refresh_from_db()
    assert created.outbox.status == OutboxStatus.PUBLISHING
    assert created.outbox.attempts == 1


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_broker_failure_is_durable_and_duplicate_effect_is_idempotent() -> None:
    user = User.objects.create_user(username="durability-test")
    created = create_checkpoint(user, "operations.checkpoint:postgres-durability")

    assert dispatch_outbox_batch(publisher=OfflineBroker(), worker_id="publisher") == 0
    created.outbox.refresh_from_db()
    assert created.outbox.status == OutboxStatus.FAILED
    assert created.outbox.available_at > timezone.now()
    assert TaskOutbox.objects.filter(pk=created.outbox.pk).exists()

    envelope = build_envelope(created.outbox)
    assert execute_checkpoint_command(envelope) is True
    assert execute_checkpoint_command(envelope) is False
    assert PipelineStepRun.objects.filter(pipeline_run=created.pipeline_run).count() == 1
    assert AuditEvent.objects.filter(action="operations.checkpoint_completed").count() == 1
