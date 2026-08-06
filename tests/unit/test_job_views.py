import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, override_settings

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.jobs.models import JobPosting
from apps.jobs.services import execute_source_parse
from apps.operations.commands import JOBS_PARSE_COMMAND_TYPE
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.sources.services import execute_source_fetch
from tests.unit.test_job_services import ASHBY_FIXTURE, FixtureFetcher, submit_ashby


def create_normalized_job(user: User, tmp_path: object) -> JobPosting:
    submission = submit_ashby(user, f"jobs.views:{user.username}")
    assert submission.pipeline_run is not None
    with override_settings(MEDIA_ROOT=tmp_path):
        execute_source_fetch(
            build_envelope(TaskOutbox.objects.get(pipeline_run=submission.pipeline_run)),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=FixtureFetcher(ASHBY_FIXTURE.read_bytes()),
        )
        parse_outbox = TaskOutbox.objects.get(command_type=JOBS_PARSE_COMMAND_TYPE)
        execute_source_parse(build_envelope(parse_outbox))
    return JobPosting.objects.get()


@pytest.mark.django_db
def test_job_pages_require_authentication() -> None:
    client = Client()

    assert client.get("/jobs/").status_code == 302


@pytest.mark.django_db
def test_viewer_can_navigate_normalized_job_provenance_without_raw_source(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="job-viewer")
    assign_team_role(user=user, role=TeamRoleName.VIEWER, actor=None, reason="test_fixture")
    posting = create_normalized_job(user, tmp_path)
    client = Client()
    client.force_login(user)

    listing = client.get("/jobs/")
    detail = client.get(f"/jobs/{posting.pk}/")
    company = client.get(f"/companies/{posting.company_id}/")
    endpoint = client.get(f"/sources/endpoints/{posting.primary_source_endpoint_id}/")

    assert listing.status_code == 200
    assert b"Director of Brand" in listing.content
    assert detail.status_code == 200
    assert b"Source-backed job content" in detail.content
    assert b"Raw fetched HTML is isolated" in detail.content
    assert b"Change timeline" in detail.content
    assert b"Created" in detail.content
    assert b"Duplicate relationships" in detail.content
    assert b"<script" not in detail.content
    assert company.status_code == 200
    assert b"Canonical job postings" in company.content
    assert endpoint.status_code == 200
    assert b"Deterministic processing" in endpoint.content
    assert b"ashby" in endpoint.content
