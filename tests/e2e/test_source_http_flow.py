import re
from uuid import uuid4

import pytest
import requests
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.sources.models import CandidateStatus, SourceCandidate


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_unsafe_public_source_is_blocked_over_real_http_without_network_command(
    live_server: object,
) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    password = uuid4().hex
    user = User.objects.create_user(username="e2e-source-operator", password=password)
    assign_team_role(
        user=user,
        role=TeamRoleName.RESEARCHER,
        actor=None,
        reason="e2e_fixture",
    )
    session = requests.Session()
    base_url = str(live_server)
    login = session.get(f"{base_url}/accounts/login/", timeout=5)
    login_csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login.text)
    assert login_csrf is not None
    signed_in = session.post(
        f"{base_url}/accounts/login/",
        data={
            "username": user.username,
            "password": password,
            "csrfmiddlewaretoken": login_csrf.group(1),
        },
        headers={"Referer": f"{base_url}/accounts/login/"},
        timeout=5,
    )
    assert signed_in.status_code == 200

    form_page = session.get(f"{base_url}/sources/submit/", timeout=5)
    csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form_page.text)
    idempotency = re.search(r'name="idempotency_key" value="([^"]+)"', form_page.text)
    assert csrf is not None
    assert idempotency is not None
    blocked = session.post(
        f"{base_url}/sources/submit/",
        data={
            "requested_url": "https://127.0.0.1/private",
            "company_name": "Blocked target",
            "company_domain": "blocked.example",
            "public_source_confirmed": "on",
            "idempotency_key": idempotency.group(1),
            "csrfmiddlewaretoken": csrf.group(1),
        },
        headers={"Referer": f"{base_url}/sources/submit/"},
        timeout=5,
    )

    assert blocked.status_code == 200
    assert "No network command was created" in blocked.text
    candidate = SourceCandidate.objects.get()
    assert candidate.status == CandidateStatus.UNSAFE
    assert candidate.pipeline_run is None
