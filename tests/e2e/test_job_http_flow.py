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
from apps.jobs.models import JobPosting
from apps.jobs.services import execute_source_parse
from apps.operations.commands import JOBS_PARSE_COMMAND_TYPE
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.sources.services import execute_source_fetch
from tests.unit.test_job_services import ASHBY_FIXTURE, FixtureFetcher, submit_ashby


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_normalized_job_provenance_is_available_over_real_http(
    live_server: object, tmp_path
) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    password = uuid4().hex
    user = User.objects.create_user(username="e2e-job-viewer", password=password)
    assign_team_role(user=user, role=TeamRoleName.VIEWER, actor=None, reason="e2e_fixture")
    submission = submit_ashby(user, "jobs.e2e:provenance")
    assert submission.pipeline_run is not None
    with override_settings(MEDIA_ROOT=tmp_path):
        execute_source_fetch(
            build_envelope(TaskOutbox.objects.get(pipeline_run=submission.pipeline_run)),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=FixtureFetcher(ASHBY_FIXTURE.read_bytes()),
        )
        execute_source_parse(
            build_envelope(TaskOutbox.objects.get(command_type=JOBS_PARSE_COMMAND_TYPE))
        )
    posting = JobPosting.objects.get()

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

    detail = client.get(f"{live_server}/jobs/{posting.pk}/", timeout=5)
    source = client.get(
        f"{live_server}/sources/endpoints/{posting.primary_source_endpoint_id}/", timeout=5
    )

    assert detail.status_code == 200
    assert "Director of Brand" in detail.text
    assert "Source-backed job content" in detail.text
    assert "Raw fetched HTML is isolated" in detail.text
    assert source.status_code == 200
    assert "Deterministic processing" in source.text
