from __future__ import annotations

from typing import Any

from celery import shared_task
from django.db import OperationalError

from apps.contacts.services import (
    execute_buyer_role_inference,
    execute_contact_source_scan,
    mark_contact_pipeline_failed,
)
from apps.operations.contracts import TaskEnvelopeV2


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="contacts.infer_roles",
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
def infer_roles_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    try:
        execute_buyer_role_inference(envelope)
    except OperationalError:
        raise
    except Exception as exc:
        mark_contact_pipeline_failed(pipeline_run_id=envelope.pipeline_run_id, error=exc)


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="contacts.scan_source",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=70,
    time_limit=85,
)
def scan_source_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    try:
        execute_contact_source_scan(envelope)
    except OperationalError:
        raise
    except Exception as exc:
        mark_contact_pipeline_failed(pipeline_run_id=envelope.pipeline_run_id, error=exc)
