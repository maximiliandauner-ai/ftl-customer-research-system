import re
from uuid import uuid4

import pytest
import requests
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.signals.models import SignalEvent
from tests.unit.test_job_services import poll_ashby
from tests.unit.test_signal_services import ashby_body, execute_only_signal_command


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_observed_signal_and_exact_evidence_are_available_over_real_http(
    live_server: object, tmp_path
) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    password = uuid4().hex
    user = User.objects.create_user(username="e2e-signal-viewer", password=password)
    assign_team_role(user=user, role=TeamRoleName.VIEWER, actor=None, reason="e2e_fixture")
    description = "Design workflow automation and maintain a governed knowledge base."
    poll_ashby(user, "signals.e2e:observed", ashby_body(description), tmp_path)
    execute_only_signal_command()
    signal = SignalEvent.objects.get()

    client = requests.Session()
    login = client.get(f"{live_server}/accounts/login/", timeout=5)
    csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login.text)
    assert csrf is not None
    signed_in = client.post(
        f"{live_server}/accounts/login/",
        data={
            "username": user.username,
            "password": password,
            "csrfmiddlewaretoken": csrf.group(1),
        },
        headers={"Referer": f"{live_server}/accounts/login/"},
        timeout=5,
    )
    assert signed_in.status_code == 200

    inbox = client.get(f"{live_server}/signals/", timeout=5)
    detail = client.get(f"{live_server}/signals/{signal.pk}/", timeout=5)
    company = client.get(f"{live_server}/companies/{signal.company_id}/", timeout=5)

    assert inbox.status_code == 200
    assert "Signal Inbox" in inbox.text
    assert signal.company.name in inbox.text
    assert detail.status_code == 200
    assert description in detail.text
    assert "EV-000002" in detail.text
    assert "Prompt 2.0.0" in detail.text
    assert company.status_code == 200
    assert "Observed signals" in company.text
