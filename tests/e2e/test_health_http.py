import json
import re
from urllib.request import urlopen
from uuid import uuid4

import pytest
import requests
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_health_endpoints_over_http(live_server: object) -> None:
    base_url = str(live_server)
    with urlopen(f"{base_url}/health/live", timeout=5) as response:  # noqa: S310
        assert response.status == 200
        assert json.load(response) == {"status": "live"}
    with urlopen(f"{base_url}/health/ready", timeout=5) as response:  # noqa: S310
        assert response.status == 200
        assert json.load(response)["status"] == "ready"
    with urlopen(f"{base_url}/static/css/app.css", timeout=5) as response:  # noqa: S310
        assert response.status == 200
        assert response.headers["Content-Type"].startswith("text/css")
        assert b"--accent" in response.read()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_authenticated_checkpoint_flow_over_real_http(live_server: object) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    operator_password = uuid4().hex
    user = User.objects.create_user(
        username="e2e-operator",
        password=operator_password,
    )
    assign_team_role(
        user=user,
        role=TeamRoleName.RESEARCHER,
        actor=None,
        reason="e2e_fixture",
    )
    session = requests.Session()
    base_url = str(live_server)

    login_page = session.get(f"{base_url}/accounts/login/", timeout=5)
    login_csrf = re.search(
        r'name="csrfmiddlewaretoken" value="([^"]+)"',
        login_page.text,
    )
    assert login_csrf is not None
    signed_in = session.post(
        f"{base_url}/accounts/login/",
        data={
            "username": "e2e-operator",
            "password": operator_password,
            "csrfmiddlewaretoken": login_csrf.group(1),
        },
        headers={"Referer": f"{base_url}/accounts/login/"},
        timeout=5,
    )
    assert signed_in.status_code == 200
    assert "Opportunity control room" in signed_in.text

    operations = session.get(f"{base_url}/operations/", timeout=5)
    command_key = re.search(
        r'name="idempotency_key" value="([^"]+)"',
        operations.text,
    )
    command_csrf = re.search(
        r'name="csrfmiddlewaretoken" value="([^"]+)"',
        operations.text,
    )
    assert command_key is not None
    assert command_csrf is not None
    completed = session.post(
        f"{base_url}/operations/commands/checkpoint/",
        data={
            "idempotency_key": command_key.group(1),
            "csrfmiddlewaretoken": command_csrf.group(1),
        },
        headers={"Referer": f"{base_url}/operations/"},
        timeout=5,
    )

    assert completed.status_code == 200
    assert "checkpoint_queued" in completed.text
    assert "operations.complete_checkpoint" in completed.text
    assert "Content-Security-Policy" in completed.headers
