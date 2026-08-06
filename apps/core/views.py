import os

import redis
from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django_celery_beat.models import PeriodicTask

from apps.operations.models import OutboxStatus, PipelineRun, TaskOutbox
from config.celery import app as celery_app


@require_GET
@never_cache
def live(_request: object) -> JsonResponse:
    return JsonResponse({"status": "live"})


def _database_and_migrations_ready() -> tuple[bool, bool]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    executor = MigrationExecutor(connection)
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return True, not pending


def _storage_ready() -> bool:
    media_root = settings.MEDIA_ROOT
    return media_root.exists() and os.access(media_root, os.W_OK)


@require_GET
@never_cache
def ready(_request: object) -> JsonResponse:
    database_ready = False
    migrations_ready = False
    storage_ready = False
    try:
        database_ready, migrations_ready = _database_and_migrations_ready()
    except Exception:  # Readiness must map dependency failures to a safe 503 response.
        database_ready = False
    try:
        storage_ready = _storage_ready()
    except OSError:
        storage_ready = False
    configuration_ready = not settings.RUNTIME_SETTINGS.safe_validation_errors()
    is_ready = database_ready and migrations_ready and storage_ready and configuration_ready
    return JsonResponse(
        {
            "status": "ready" if is_ready else "unavailable",
            "checks": {
                "configuration": configuration_ready,
                "database": database_ready,
                "migrations": migrations_ready,
                "storage": storage_ready,
            },
        },
        status=200 if is_ready else 503,
    )


def _broker_ready() -> bool:
    client = redis.Redis.from_url(
        settings.RUNTIME_SETTINGS.celery_broker_url.get_secret_value(),
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        return bool(client.ping())
    finally:
        client.close()


@login_required
@permission_required("operations.view_dependency_health", raise_exception=True)
@require_GET
@never_cache
def dependencies(_request: HttpRequest) -> JsonResponse:
    checks: dict[str, object] = {}
    try:
        database_ready, migrations_ready = _database_and_migrations_ready()
    except Exception:
        database_ready, migrations_ready = False, False
    checks["database"] = database_ready
    checks["migrations"] = migrations_ready
    checks["storage"] = _storage_ready()
    try:
        checks["broker"] = _broker_ready()
    except Exception:
        checks["broker"] = False
    try:
        worker_replies = celery_app.control.ping(timeout=0.5)
        worker_count = len(worker_replies or [])
    except Exception:
        worker_count = 0
    checks["workers"] = worker_count
    beat_schedule_count = PeriodicTask.objects.filter(
        name__in=(
            "FTL outbox dispatch",
            "FTL stale outbox recovery",
            "FTL daily source discovery",
        ),
        enabled=True,
    ).count()
    checks["beat_schedules"] = beat_schedule_count
    checks["outbox"] = {
        "pending": TaskOutbox.objects.filter(status=OutboxStatus.PENDING).count(),
        "publishing": TaskOutbox.objects.filter(status=OutboxStatus.PUBLISHING).count(),
        "failed": TaskOutbox.objects.filter(status=OutboxStatus.FAILED).count(),
    }
    checks["active_runs"] = PipelineRun.objects.filter(
        status__in=("queued", "running", "waiting_external")
    ).count()
    checks["openai"] = (
        "enabled" if settings.RUNTIME_SETTINGS.features.openai_enabled else "disabled_by_policy"
    )
    required_ready = all(
        (
            bool(checks["database"]),
            bool(checks["migrations"]),
            bool(checks["storage"]),
            bool(checks["broker"]),
            worker_count > 0,
            beat_schedule_count == 3,
        )
    )
    return JsonResponse(
        {"status": "healthy" if required_ready else "degraded", "checks": checks},
        status=200 if required_ready else 503,
    )
