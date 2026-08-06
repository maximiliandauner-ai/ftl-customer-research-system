import json
import re
from uuid import uuid4

import pytest
import requests
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.operations.commands import (
    COMPANIES_AGGREGATE_COMMAND_TYPE,
    SIGNALS_CLASSIFY_COMMAND_TYPE,
)
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.opportunities.models import Opportunity
from apps.opportunities.services import execute_company_aggregation
from apps.signals.classification import execute_signal_classification
from apps.signals.services import execute_signal_detection
from tests.unit.test_job_services import ASHBY_FIXTURE, poll_ashby


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_ranked_opportunity_and_assessment_are_available_over_real_http(
    live_server: object, tmp_path
) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    password = uuid4().hex
    user = User.objects.create_user(username="e2e-opportunity-viewer", password=password)
    assign_team_role(user=user, role=TeamRoleName.VIEWER, actor=None, reason="e2e_fixture")
    payload = json.loads(ASHBY_FIXTURE.read_text())
    payload["jobs"][0]["descriptionPlain"] = (
        "Design workflow automation, knowledge management, and data integration."
    )
    poll_ashby(user, "opportunities.e2e:ranked", json.dumps(payload).encode(), tmp_path)
    execute_signal_detection(build_envelope(TaskOutbox.objects.get(command_type="signals.detect")))
    execute_signal_classification(
        build_envelope(TaskOutbox.objects.get(command_type=SIGNALS_CLASSIFY_COMMAND_TYPE))
    )
    execute_company_aggregation(
        build_envelope(TaskOutbox.objects.get(command_type=COMPANIES_AGGREGATE_COMMAND_TYPE))
    )
    opportunity = Opportunity.objects.get()

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

    ranking = client.get(f"{live_server}/opportunities/", timeout=5)
    detail = client.get(f"{live_server}/opportunities/{opportunity.pk}/", timeout=5)
    signal = client.get(f"{live_server}/signals/{opportunity.primary_signal_id}/", timeout=5)

    assert ranking.status_code == 200
    assert "Deterministic ranking" in ranking.text
    assert opportunity.company.name in ranking.text
    assert detail.status_code == 200
    assert "Decomposable score" in detail.text
    assert "Feature snapshot" in detail.text
    assert "vendor_partner_receptivity" in detail.text
    assert signal.status_code == 200
    assert "Capability assessment" in signal.text
    assert "Evidence EV-" in signal.text
