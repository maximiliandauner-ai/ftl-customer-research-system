from __future__ import annotations

from typing import Any

from celery import shared_task
from django.db import OperationalError

from apps.jobs.services import RetryableParseError, execute_source_parse, mark_parse_exhausted
from apps.operations.contracts import TaskEnvelopeV2


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="jobs.parse_source_snapshot",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=90,
    time_limit=120,
)
def parse_source_snapshot_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    delivery_info = getattr(task.request, "delivery_info", {}) or {}
    recover_started = bool(delivery_info.get("redelivered")) or task.request.retries > 0
    try:
        execute_source_parse(envelope, recover_started=recover_started)
    except RetryableParseError as exc:
        if task.request.retries >= task.max_retries:
            mark_parse_exhausted(pipeline_run_id=envelope.pipeline_run_id)
            return
        countdown = min(15 * (2**task.request.retries), 120)
        raise task.retry(exc=exc, countdown=countdown) from exc
