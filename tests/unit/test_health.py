from unittest.mock import patch

import pytest
from django.test import Client


def test_liveness_does_not_access_dependencies() -> None:
    response = Client().get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert response.headers["Cache-Control"] == (
        "max-age=0, no-cache, no-store, must-revalidate, private"
    )


@pytest.mark.django_db
def test_readiness_reports_database_and_migrations() -> None:
    response = Client().get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "configuration": True,
            "database": True,
            "migrations": True,
            "storage": True,
        },
    }


def test_readiness_is_unavailable_for_pending_migrations() -> None:
    with patch("apps.core.views._database_and_migrations_ready", return_value=(True, False)):
        response = Client().get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["migrations"] is False


def test_readiness_safely_maps_database_failure() -> None:
    with patch(
        "apps.core.views._database_and_migrations_ready", side_effect=RuntimeError("private DSN")
    ):
        response = Client().get("/health/ready")

    assert response.status_code == 503
    assert b"private DSN" not in response.content
    assert response.json()["checks"]["database"] is False


def test_readiness_is_unavailable_when_storage_is_not_writable() -> None:
    with patch("apps.core.views._storage_ready", return_value=False):
        response = Client().get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["storage"] is False
