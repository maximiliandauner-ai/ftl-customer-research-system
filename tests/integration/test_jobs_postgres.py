import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.db import DatabaseError, connection, transaction
from django.test import override_settings

from apps.jobs.models import JobPostingSnapshot, PostingChangeEvent
from apps.jobs.services import execute_source_parse
from apps.operations.commands import JOBS_PARSE_COMMAND_TYPE
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.sources.services import execute_source_fetch
from tests.unit.test_job_services import ASHBY_FIXTURE, FixtureFetcher, submit_ashby


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_normalized_snapshot_trigger_rejects_mutation(tmp_path) -> None:
    assert connection.vendor == "postgresql"
    user = User.objects.create_user(username="job-trigger-test")
    submission = submit_ashby(user, "jobs.postgres:trigger")
    assert submission.pipeline_run is not None
    with override_settings(MEDIA_ROOT=tmp_path):
        execute_source_fetch(
            build_envelope(TaskOutbox.objects.get(pipeline_run=submission.pipeline_run)),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=FixtureFetcher(ASHBY_FIXTURE.read_bytes()),
        )
        parse_outbox = TaskOutbox.objects.get(command_type=JOBS_PARSE_COMMAND_TYPE)
        execute_source_parse(build_envelope(parse_outbox))
    snapshot = JobPostingSnapshot.objects.get()

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE jobs_jobpostingsnapshot SET title = %s WHERE id = %s",
            ["Mutated", snapshot.pk],
        )

    snapshot.refresh_from_db()
    assert snapshot.title == "Director of Brand"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_change_event_trigger_rejects_mutation(tmp_path) -> None:
    assert connection.vendor == "postgresql"
    user = User.objects.create_user(username="job-change-trigger-test")
    submission = submit_ashby(user, "jobs.postgres:change-trigger")
    assert submission.pipeline_run is not None
    with override_settings(MEDIA_ROOT=tmp_path):
        execute_source_fetch(
            build_envelope(TaskOutbox.objects.get(pipeline_run=submission.pipeline_run)),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=FixtureFetcher(ASHBY_FIXTURE.read_bytes()),
        )
        parse_outbox = TaskOutbox.objects.get(command_type=JOBS_PARSE_COMMAND_TYPE)
        execute_source_parse(build_envelope(parse_outbox))
    event = PostingChangeEvent.objects.get()

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE jobs_postingchangeevent SET policy_version = %s WHERE id = %s",
            ["mutated", event.pk],
        )

    event.refresh_from_db()
    assert event.policy_version == "1.0.0"
