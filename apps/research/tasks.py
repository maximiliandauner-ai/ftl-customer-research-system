from __future__ import annotations

from typing import Any

from celery import shared_task
from django.db import OperationalError

from apps.operations.contracts import TaskEnvelopeV2
from apps.research.services import (
    execute_public_research,
    execute_research_extraction,
    mark_research_failed,
)


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="research.run_public",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=165,
    time_limit=180,
)
def run_public_research_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    try:
        execute_public_research(envelope)
    except OperationalError:
        raise
    except Exception as exc:
        mark_research_failed(
            pipeline_run_id=envelope.pipeline_run_id,
            error=exc,
            extraction=False,
        )


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="research.extract",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=105,
    time_limit=120,
)
def extract_research_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    try:
        execute_research_extraction(envelope)
    except OperationalError:
        raise
    except Exception as exc:
        mark_research_failed(
            pipeline_run_id=envelope.pipeline_run_id,
            error=exc,
            extraction=True,
        )
