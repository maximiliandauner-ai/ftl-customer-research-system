from __future__ import annotations

from typing import Any

from celery import shared_task
from django.conf import settings
from django.db import OperationalError

from apps.companies.services import (
    RetryableCompanyEnrichmentError,
    execute_company_enrichment,
    mark_company_enrichment_exhausted,
    schedule_due_company_enrichments,
)
from apps.operations.contracts import TaskEnvelopeV2


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="companies.enrich_profile",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=120,
    time_limit=150,
)
def enrich_company_profile_task(task: Any, envelope_data: dict[str, object]) -> None:
    envelope = TaskEnvelopeV2.model_validate(envelope_data)
    delivery_info = getattr(task.request, "delivery_info", {}) or {}
    recover_started = bool(delivery_info.get("redelivered")) or task.request.retries > 0
    try:
        execute_company_enrichment(
            envelope,
            policy=settings.RUNTIME_SETTINGS.fetch,
            recover_started=recover_started,
        )
    except RetryableCompanyEnrichmentError as exc:
        if task.request.retries >= task.max_retries:
            mark_company_enrichment_exhausted(pipeline_run_id=envelope.pipeline_run_id)
            return
        countdown = min(15 * (2**task.request.retries), 120)
        raise task.retry(exc=exc, countdown=countdown) from exc


@shared_task(  # type: ignore[untyped-decorator]
    name="companies.schedule_profile_refresh",
    ignore_result=True,
    soft_time_limit=45,
    time_limit=60,
)
def schedule_company_profile_refresh_task() -> None:
    schedule_due_company_enrichments(limit=500)
