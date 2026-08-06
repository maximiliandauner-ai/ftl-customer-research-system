import re
from uuid import uuid4

import pytest
import requests
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.knowledge.services import activate_knowledge_release, sync_knowledge_release
from apps.operations.commands import ASSET_MATCH_COMMAND_TYPE, SOLUTION_DESIGN_COMMAND_TYPE
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.solutions.models import SolutionVersion
from apps.solutions.services import (
    execute_asset_matching,
    execute_solution_design,
    request_solution_design,
)
from tests.unit.test_knowledge_solution_services import SOURCE_ROOT, _complete_research
from tests.unit.test_research_services import _runtime


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_knowledge_asset_and_solution_workspace_is_available_over_real_http(
    live_server: object, tmp_path
) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    password = uuid4().hex
    user = User.objects.create_user(username="e2e-solution-viewer", password=password)
    assign_team_role(user=user, role=TeamRoleName.VIEWER, actor=None, reason="e2e_fixture")
    with override_settings(RUNTIME_SETTINGS=_runtime(enabled=True), MEDIA_ROOT=tmp_path):
        opportunity, _research = _complete_research(user, tmp_path)
        release = sync_knowledge_release(
            source_root=SOURCE_ROOT,
            source_commit="abcde92",
            actor=user,
        ).release
        activate_knowledge_release(
            release_id=release.pk,
            actor=user,
            reason="Reviewed E2E knowledge release fixture.",
        )
        request_solution_design(opportunity_id=opportunity.pk, actor=user)
        execute_solution_design(
            build_envelope(TaskOutbox.objects.get(command_type=SOLUTION_DESIGN_COMMAND_TYPE))
        )
        execute_asset_matching(
            build_envelope(TaskOutbox.objects.get(command_type=ASSET_MATCH_COMMAND_TYPE))
        )
        solution = SolutionVersion.objects.get()

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
        knowledge = client.get(f"{live_server}/knowledge/{release.pk}/", timeout=5)
        solutions = client.get(f"{live_server}/solutions/", timeout=5)
        detail = client.get(f"{live_server}/solutions/{solution.pk}/", timeout=5)
        opportunity_page = client.get(f"{live_server}/opportunities/{opportunity.pk}/", timeout=5)

    assert knowledge.status_code == 200
    assert "Asset database" in knowledge.text
    assert "intentionally contains no assets" in knowledge.text
    assert solutions.status_code == 200
    assert "Solution versions" in solutions.text
    assert detail.status_code == 200
    assert "Valid zero-asset result" in detail.text
    assert "Pilot + Production System" not in detail.text or "pilot_plus_system" in detail.text
    assert opportunity_page.status_code == 200
    assert "Solution & asset match" in opportunity_page.text
