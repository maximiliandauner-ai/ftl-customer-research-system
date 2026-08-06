import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.operations.contracts import CreateCheckpointCommandV1
from apps.operations.models import AuditEvent, OutboxStatus, PipelineRun, TaskOutbox
from apps.operations.services import create_checkpoint_command


def role_user(username: str, role: TeamRoleName) -> User:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username=username, password="test-password-123")
    assign_team_role(user=user, role=role, actor=None, reason="test_fixture")
    return user


@pytest.mark.django_db
def test_product_pages_require_authentication() -> None:
    client = Client()

    assert client.get("/").status_code == 302
    assert client.get("/operations/").status_code == 302
    assert client.get("/health/dependencies").status_code == 302
    assert client.get("/health/live").status_code == 200


@pytest.mark.django_db
def test_authenticated_user_without_role_receives_explicit_403() -> None:
    user = User.objects.create_user(username="no-role")
    client = Client()
    client.force_login(user)

    response = client.get("/")

    assert response.status_code == 403
    assert b"Permission required" in response.content


@pytest.mark.django_db
def test_viewer_can_read_operations_but_cannot_trigger_command() -> None:
    user = role_user("viewer", TeamRoleName.VIEWER)
    client = Client()
    client.force_login(user)

    response = client.get("/operations/")
    forbidden = client.post(
        "/operations/commands/checkpoint/",
        {"idempotency_key": "operations.checkpoint:viewer"},
    )

    assert response.status_code == 200
    assert b"Durable command center" in response.content
    assert forbidden.status_code == 403
    assert PipelineRun.objects.count() == 0


@pytest.mark.django_db
def test_researcher_creates_correlated_checkpoint_through_csrf_form() -> None:
    user = role_user("researcher", TeamRoleName.RESEARCHER)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    page = client.get("/operations/")
    csrf_token = page.cookies["csrftoken"].value
    request_id = str(uuid.uuid4())

    response = client.post(
        "/operations/commands/checkpoint/",
        {"idempotency_key": "operations.checkpoint:web", "csrfmiddlewaretoken": csrf_token},
        HTTP_X_REQUEST_ID=request_id,
    )

    assert response.status_code == 302
    run = PipelineRun.objects.get()
    assert str(run.request_id) == request_id
    assert response.headers["X-Request-ID"] == request_id
    detail = client.get(response.headers["Location"])
    assert detail.status_code == 200
    assert b"checkpoint_queued" in detail.content
    assert b"operations.complete_checkpoint" in detail.content


@pytest.mark.django_db
def test_checkpoint_post_requires_csrf() -> None:
    user = role_user("csrf", TeamRoleName.RESEARCHER)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    response = client.post(
        "/operations/commands/checkpoint/",
        {"idempotency_key": "operations.checkpoint:no-csrf"},
    )

    assert response.status_code == 403
    assert PipelineRun.objects.count() == 0


@pytest.mark.django_db
def test_founder_can_retry_failed_command_and_view_audit() -> None:
    user = role_user("founder", TeamRoleName.FOUNDER)
    created = create_checkpoint_command(
        command=CreateCheckpointCommandV1(idempotency_key="operations.checkpoint:retry-ui"),
        actor=user,
    )
    TaskOutbox.objects.filter(pk=created.outbox.pk).update(
        status=OutboxStatus.FAILED,
        attempts=3,
        last_error_code="OUTBOX_PUBLISH_FAILED",
        last_error_message="Connection refused",
    )
    client = Client()
    client.force_login(user)

    detail = client.get(f"/operations/outbox/{created.outbox.pk}/")
    retry = client.post(
        f"/operations/outbox/{created.outbox.pk}/retry/",
        {"reason": "manual_operational_retry"},
    )
    audit = client.get("/operations/audit/?action=operations.outbox_retry_requested")

    assert detail.status_code == 200
    assert b"OUTBOX_PUBLISH_FAILED" in detail.content
    assert retry.status_code == 302
    created.outbox.refresh_from_db()
    assert created.outbox.status == OutboxStatus.PENDING
    assert b"operations.outbox_retry_requested" in audit.content


@pytest.mark.django_db
def test_lists_filter_and_unknown_records_return_404() -> None:
    user = role_user("list-reader", TeamRoleName.VIEWER)
    client = Client()
    client.force_login(user)

    assert client.get("/operations/runs/?status=complete").status_code == 200
    assert client.get("/operations/outbox/?status=failed").status_code == 200
    assert client.get(f"/operations/runs/{uuid.uuid4()}/").status_code == 404
    assert client.get(f"/operations/outbox/{uuid.uuid4()}/").status_code == 404


@pytest.mark.django_db
def test_security_headers_and_request_id_are_present() -> None:
    user = role_user("headers", TeamRoleName.VIEWER)
    client = Client()
    client.force_login(user)

    response = client.get("/", HTTP_X_REQUEST_ID="not-a-safe-request-id")

    assert response.status_code == 200
    uuid.UUID(response.headers["X-Request-ID"])
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert "script-src 'none'" in response.headers["Content-Security-Policy"]


@pytest.mark.django_db
def test_dependency_health_is_permissioned_and_reports_safe_state() -> None:
    user = role_user("health-reader", TeamRoleName.VIEWER)
    client = Client()
    client.force_login(user)

    with (
        patch("apps.core.views._broker_ready", return_value=True),
        patch("apps.core.views.celery_app.control.ping", return_value=[{"worker": {"ok": "pong"}}]),
    ):
        response = client.get("/health/dependencies")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["checks"]["beat_schedules"] == 2
    assert payload["checks"]["workers"] == 1
    assert payload["checks"]["openai"] == "disabled_by_policy"
    assert "password" not in response.content.decode().lower()


@pytest.mark.django_db
def test_dependency_health_maps_failures_to_degraded_without_exception_text() -> None:
    user = role_user("health-failure", TeamRoleName.VIEWER)
    client = Client()
    client.force_login(user)

    with (
        patch("apps.core.views._broker_ready", side_effect=RuntimeError("password=private")),
        patch("apps.core.views.celery_app.control.ping", side_effect=RuntimeError("private")),
    ):
        response = client.get("/health/dependencies")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert b"private" not in response.content
    assert AuditEvent.objects.filter(action="accounts.team_role_assigned").exists()
