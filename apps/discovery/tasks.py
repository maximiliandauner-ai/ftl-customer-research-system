from __future__ import annotations

from typing import Any

from celery import shared_task

from apps.discovery.services import DiscoveryLeaseBusy, execute_discovery, schedule_daily_runs
from apps.operations.contracts import TaskEnvelopeV2


@shared_task(  # type: ignore[untyped-decorator]
    name="discovery.schedule_daily",
    ignore_result=True,
    soft_time_limit=30,
    time_limit=45,
)
def schedule_daily_discovery_task() -> None:
    schedule_daily_runs()


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="discovery.execute",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=120,
    time_limit=150,
)
def execute_discovery_task(_task: Any, envelope_data: dict[str, object]) -> None:
    try:
        execute_discovery(
            TaskEnvelopeV2.model_validate(envelope_data),
            lease_owner=f"celery:{_task.request.id}",
        )
    except DiscoveryLeaseBusy as exc:
        raise _task.retry(exc=exc, countdown=60, max_retries=5) from exc
