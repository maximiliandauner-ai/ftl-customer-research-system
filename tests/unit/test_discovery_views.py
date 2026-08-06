import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.discovery.models import DiscoveryRun, SearchDefinition
from apps.operations.models import TaskOutbox


@pytest.mark.django_db
def test_researcher_can_queue_and_inspect_manual_discovery() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="discovery-researcher", password="fixture-password")
    assign_team_role(
        user=user,
        role=TeamRoleName.RESEARCHER,
        actor=None,
        reason="test_access",
    )
    definition = SearchDefinition.objects.get(active=True)
    client = Client()
    client.force_login(user)

    index = client.get("/discovery/")
    response = client.post(f"/discovery/definitions/{definition.pk}/run/", follow=True)

    assert index.status_code == 200
    assert b"Company and job discovery" in index.content
    assert response.status_code == 200
    assert b"queued through the durable outbox" in response.content
    assert DiscoveryRun.objects.count() == 1
    assert TaskOutbox.objects.filter(command_type="discovery.execute").count() == 1


@pytest.mark.django_db
def test_viewer_cannot_trigger_discovery() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="discovery-viewer")
    assign_team_role(user=user, role=TeamRoleName.VIEWER, actor=None, reason="test_access")
    definition = SearchDefinition.objects.get(active=True)
    client = Client()
    client.force_login(user)

    response = client.post(f"/discovery/definitions/{definition.pk}/run/")

    assert response.status_code == 403
    assert DiscoveryRun.objects.count() == 0
