from __future__ import annotations

from typing import Any

from celery import shared_task
from django.db import OperationalError

from apps.operations.contracts import TaskEnvelopeV2
from apps.signals.classification import (
    execute_signal_classification,
    mark_classification_failed,
)
from apps.signals.services import execute_signal_detection, mark_detection_failed


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="signals.detect_posting_change",
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
def detect_posting_change_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    try:
        execute_signal_detection(envelope)
    except OperationalError:
        raise
    except Exception as exc:
        mark_detection_failed(pipeline_run_id=envelope.pipeline_run_id, error=exc)


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="signals.classify_signal",
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
def classify_signal_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    try:
        execute_signal_classification(envelope)
    except OperationalError:
        raise
    except Exception as exc:
        mark_classification_failed(pipeline_run_id=envelope.pipeline_run_id, error=exc)
