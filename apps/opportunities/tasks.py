from __future__ import annotations

from typing import Any

from celery import shared_task
from django.db import OperationalError

from apps.operations.contracts import TaskEnvelopeV2
from apps.opportunities.services import execute_company_aggregation, mark_aggregation_failed


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="opportunities.aggregate_company",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=45,
    time_limit=60,
)
def aggregate_company_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    try:
        execute_company_aggregation(envelope)
    except OperationalError:
        raise
    except Exception as exc:
        mark_aggregation_failed(pipeline_run_id=envelope.pipeline_run_id, error=exc)
