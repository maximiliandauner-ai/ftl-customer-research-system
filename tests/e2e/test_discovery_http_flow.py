import re
from uuid import uuid4

import pytest
import requests
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.discovery.models import DiscoveryRun, SearchDefinition
from apps.operations.models import TaskOutbox


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_researcher_queues_discovery_over_real_http(live_server: object) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    password = uuid4().hex
    user = User.objects.create_user(username="e2e-discovery-operator", password=password)
    assign_team_role(user=user, role=TeamRoleName.RESEARCHER, actor=None, reason="e2e_fixture")
    definition = SearchDefinition.objects.get(
        definition_key="ftl-creative-learning-demand", active=True
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

    discovery = session.get(f"{base_url}/discovery/", timeout=5)
    csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', discovery.text)
    assert csrf is not None
    queued = session.post(
        f"{base_url}/discovery/definitions/{definition.pk}/run/",
        data={"csrfmiddlewaretoken": csrf.group(1)},
        headers={"Referer": f"{base_url}/discovery/"},
        timeout=5,
    )

    assert queued.status_code == 200
    assert "Discovery run" in queued.text
    assert "queued through the durable outbox" in queued.text
    run = DiscoveryRun.objects.get()
    assert str(run.pk) in queued.url
    assert TaskOutbox.objects.filter(command_type="discovery.execute").count() == 1
