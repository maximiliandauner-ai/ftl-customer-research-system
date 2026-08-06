from __future__ import annotations

from typing import Any

from celery import shared_task
from django.db import OperationalError

from apps.operations.contracts import TaskEnvelopeV2
from apps.operations.outbox import dispatch_outbox_batch, recover_stale_claims
from apps.operations.services import execute_checkpoint_command


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="operations.complete_checkpoint",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
    soft_time_limit=30,
    time_limit=45,
)
def complete_checkpoint_task(_task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    execute_checkpoint_command(envelope)


@shared_task(  # type: ignore[untyped-decorator]
    name="operations.dispatch_outbox",
    ignore_result=True,
    soft_time_limit=45,
    time_limit=60,
)
def dispatch_outbox_task() -> None:
    dispatch_outbox_batch()


@shared_task(  # type: ignore[untyped-decorator]
    name="operations.recover_stale_outbox",
    ignore_result=True,
    soft_time_limit=30,
    time_limit=45,
)
def recover_stale_outbox_task() -> None:
    recover_stale_claims()
