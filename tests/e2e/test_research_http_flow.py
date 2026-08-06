import json
import re
from uuid import uuid4

import pytest
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.operations.commands import (
    COMPANIES_AGGREGATE_COMMAND_TYPE,
    RESEARCH_EXTRACT_COMMAND_TYPE,
    RESEARCH_PUBLIC_COMMAND_TYPE,
    SIGNALS_CLASSIFY_COMMAND_TYPE,
)
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.opportunities.models import Opportunity
from apps.opportunities.services import execute_company_aggregation
from apps.research.models import ResearchRun
from apps.research.services import (
    execute_public_research,
    execute_research_extraction,
    request_standard_research,
)
from apps.signals.classification import execute_signal_classification
from apps.signals.services import execute_signal_detection
from tests.unit.test_job_services import ASHBY_FIXTURE, poll_ashby
from tests.unit.test_research_services import FixtureResearchProvider


def _enabled_runtime():
    features = settings.RUNTIME_SETTINGS.features.model_copy(
        update={
            "openai_enabled": True,
            "web_search_enabled": True,
            "standard_research_enabled": True,
        }
    )
    return settings.RUNTIME_SETTINGS.model_copy(update={"features": features})


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_completed_research_is_available_over_real_http(live_server: object, tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    password = uuid4().hex
    user = User.objects.create_user(username="e2e-research-viewer", password=password)
    assign_team_role(user=user, role=TeamRoleName.VIEWER, actor=None, reason="e2e_fixture")
    payload = json.loads(ASHBY_FIXTURE.read_text())
    payload["jobs"][0]["descriptionPlain"] = (
        "Design workflow automation, knowledge management, and data integration."
    )
    poll_ashby(user, "research.e2e:completed", json.dumps(payload).encode(), tmp_path)
    execute_signal_detection(build_envelope(TaskOutbox.objects.get(command_type="signals.detect")))
    execute_signal_classification(
        build_envelope(TaskOutbox.objects.get(command_type=SIGNALS_CLASSIFY_COMMAND_TYPE))
    )
    execute_company_aggregation(
        build_envelope(TaskOutbox.objects.get(command_type=COMPANIES_AGGREGATE_COMMAND_TYPE))
    )
    provider = FixtureResearchProvider()

    with override_settings(RUNTIME_SETTINGS=_enabled_runtime(), MEDIA_ROOT=tmp_path):
        request_standard_research(
            opportunity_id=Opportunity.objects.get().pk,
            actor=user,
        )
        execute_public_research(
            build_envelope(TaskOutbox.objects.get(command_type=RESEARCH_PUBLIC_COMMAND_TYPE)),
            provider=provider,
        )
        execute_research_extraction(
            build_envelope(TaskOutbox.objects.get(command_type=RESEARCH_EXTRACT_COMMAND_TYPE)),
            provider=provider,
        )
        research_run = ResearchRun.objects.get()
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

        listing = client.get(f"{live_server}/research/", timeout=5)
        detail = client.get(f"{live_server}/research/{research_run.pk}/", timeout=5)

    assert listing.status_code == 200
    assert "Company research" in listing.text
    assert research_run.opportunity.company.name in listing.text
    assert detail.status_code == 200
    assert "Registered public sources" in detail.text
    assert "Persisted cited report" in detail.text
    assert "CLM-000001" in detail.text
    assert "Plain text, never raw HTML" in detail.text
