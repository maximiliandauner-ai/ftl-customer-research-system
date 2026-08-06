from __future__ import annotations

from typing import Any

from celery import shared_task
from django.db import OperationalError

from apps.operations.contracts import TaskEnvelopeV2
from apps.solutions.services import (
    execute_asset_matching,
    execute_solution_design,
    mark_solution_failed,
)


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="solutions.design",
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
def design_solution_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    try:
        execute_solution_design(envelope)
    except OperationalError:
        raise
    except Exception as exc:
        mark_solution_failed(pipeline_run_id=envelope.pipeline_run_id, error=exc)


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="solutions.match_assets",
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
def match_assets_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    try:
        execute_asset_matching(envelope)
    except OperationalError:
        raise
    except Exception as exc:
        mark_solution_failed(pipeline_run_id=envelope.pipeline_run_id, error=exc)
