import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.operations.models import AuditEvent
from apps.signals.models import SignalEvent, SignalStatus
from tests.unit.test_job_services import poll_ashby
from tests.unit.test_signal_services import ashby_body, execute_only_signal_command


def role_user(username: str, role: TeamRoleName) -> User:
    user = User.objects.create_user(username=username)
    assign_team_role(user=user, role=role, actor=None, reason="signal_test_fixture")
    return user


@pytest.mark.django_db
def test_signal_pages_require_authentication() -> None:
    assert Client().get("/signals/").status_code == 302


@pytest.mark.django_db
def test_viewer_sees_exact_signal_evidence_but_cannot_retract(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    owner = User.objects.create_user(username="signal-source-owner")
    description = "Build workflow automation and a governed knowledge base."
    poll_ashby(owner, "signals.views:created", ashby_body(description), tmp_path)
    execute_only_signal_command()
    signal = SignalEvent.objects.get()
    viewer = role_user("signal-viewer", TeamRoleName.VIEWER)
    client = Client()
    client.force_login(viewer)

    listing = client.get("/signals/")
    detail = client.get(f"/signals/{signal.pk}/")
    forbidden = client.post(f"/signals/{signal.pk}/retract/", {"reason": "Not relevant"})

    assert listing.status_code == 200
    assert b"Signal Inbox" in listing.content
    assert b"Capability hiring" in listing.content
    assert detail.status_code == 200
    assert description.encode() in detail.content
    assert b"Immutable catalog quotes" in detail.content
    assert b"This is an observed source fact" in detail.content
    assert b"Retract false positive" not in detail.content
    assert forbidden.status_code == 403


@pytest.mark.django_db
def test_reviewer_retraction_requires_reason_and_preserves_evidence(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    owner = User.objects.create_user(username="signal-review-source")
    poll_ashby(
        owner,
        "signals.retract:created",
        ashby_body("Build workflow automation for operations."),
        tmp_path,
    )
    execute_only_signal_command()
    signal = SignalEvent.objects.get()
    evidence_ids = list(signal.evidence_links.values_list("evidence_item_id", flat=True))
    reviewer = role_user("signal-reviewer", TeamRoleName.REVIEWER)
    client = Client()
    client.force_login(reviewer)

    invalid = client.post(f"/signals/{signal.pk}/retract/", {"reason": "no"}, follow=True)
    assert invalid.status_code == 200
    signal.refresh_from_db()
    assert signal.status == SignalStatus.ACTIVE

    response = client.post(
        f"/signals/{signal.pk}/retract/",
        {"reason": "The requirement was classified too broadly."},
        follow=True,
    )
    signal.refresh_from_db()
    assert response.status_code == 200
    assert signal.status == SignalStatus.RETRACTED
    assert signal.review_state == "false_positive"
    assert signal.reviewed_by == reviewer
    assert list(signal.evidence_links.values_list("evidence_item_id", flat=True)) == evidence_ids
    assert AuditEvent.objects.filter(
        action="signals.false_positive_retracted", object_id=signal.pk
    ).exists()
    assert b"Observation retained for audit" in response.content
