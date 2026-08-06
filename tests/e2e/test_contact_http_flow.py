import re
from uuid import uuid4

import pytest
import requests
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.contacts.models import ContactRoute
from apps.contacts.services import (
    execute_buyer_role_inference,
    execute_contact_source_scan,
    request_contact_research,
)
from apps.operations.commands import (
    BUYER_ROLES_INFER_COMMAND_TYPE,
    CONTACT_SOURCE_SCAN_COMMAND_TYPE,
)
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from tests.unit.test_contact_services import (
    FixtureContactFetcher,
    _approved_solution,
    _contact_runtime,
)


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_contact_workspace_is_available_over_real_http(live_server: object, tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    password = uuid4().hex
    user = User.objects.create_user(username="e2e-contact-founder", password=password)
    assign_team_role(
        user=user,
        role=TeamRoleName.FOUNDER,
        actor=None,
        reason="contact_e2e_fixture",
    )
    with override_settings(RUNTIME_SETTINGS=_contact_runtime(), MEDIA_ROOT=tmp_path):
        opportunity, _solution = _approved_solution(user, tmp_path)
        scheduled = request_contact_research(opportunity_id=opportunity.pk, actor=user)
        execute_buyer_role_inference(
            build_envelope(TaskOutbox.objects.get(command_type=BUYER_ROLES_INFER_COMMAND_TYPE))
        )
        execute_contact_source_scan(
            build_envelope(TaskOutbox.objects.get(command_type=CONTACT_SOURCE_SCAN_COMMAND_TYPE)),
            fetcher=FixtureContactFetcher(
                b'<a href="mailto:info@acme.example">Official inbox</a>'
                b'<a href="https://acme.example/contact">Contact form</a>'
            ),
        )
        route = ContactRoute.objects.get(route_type="role_email")

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
        contact_list = client.get(f"{live_server}/contacts/", timeout=5)
        detail = client.get(
            f"{live_server}/contacts/{scheduled.contact_research_run.pk}/", timeout=5
        )
        company = client.get(f"{live_server}/companies/{opportunity.company_id}/", timeout=5)
        opportunity_page = client.get(f"{live_server}/opportunities/{opportunity.pk}/", timeout=5)

    assert contact_list.status_code == 200
    assert "Buyer and route intelligence" in contact_list.text
    assert detail.status_code == 200
    assert "Buyer role hypotheses" in detail.text
    assert "Categories, never people" in detail.text
    assert route.value_masked in detail.text
    assert "info@acme.example" not in detail.text
    assert "No message is generated" in detail.text or "no draft created" in detail.text
    assert company.status_code == 200
    assert "Buyer and route intelligence" in company.text
    assert opportunity_page.status_code == 200
    assert "Buyer roles & contact routes" in opportunity_page.text
