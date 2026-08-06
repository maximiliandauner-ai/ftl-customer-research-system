import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import override_settings

from apps.jobs.models import (
    ConnectorParseAttempt,
    DuplicateRelationship,
    JobLocation,
    JobPosting,
    JobPostingSnapshot,
    ParseStatus,
    PostingChangeEvent,
    PostingChangeType,
    PostingLifecycle,
    PostingObservation,
)
from apps.jobs.services import _link_exact_duplicates, execute_source_parse
from apps.operations.commands import JOBS_PARSE_COMMAND_TYPE
from apps.operations.models import AuditEvent, PipelineStatus, TaskOutbox
from apps.operations.outbox import build_envelope
from apps.sources.contracts import SafeFetchResultV1, SubmitPublicSourceV1
from apps.sources.models import EndpointStatus, SourceSnapshot
from apps.sources.services import execute_source_fetch, submit_public_source

ASHBY_FIXTURE = Path(__file__).parents[1] / "fixtures" / "connectors" / "ashby.json"
PUBLIC_IP = "93.184.216.34"


def public_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
    return (PUBLIC_IP,)


class FixtureFetcher:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self.body = body
        self.content_type = content_type

    def fetch(self, requested_url: str, *, etag: str = "", last_modified: str = ""):
        return SafeFetchResultV1(
            requested_url=requested_url,
            final_url=requested_url,
            status_code=200,
            retrieved_at_iso=datetime.now(UTC).isoformat(),
            content_type=self.content_type,
            encoding="utf-8",
            headers_filtered={},
            body=self.body,
            body_sha256=hashlib.sha256(self.body).hexdigest(),
            body_size_bytes=len(self.body),
            elapsed_ms=5,
            redirect_chain=[],
        )


def submit_ashby(user: User, key: str):
    return submit_public_source(
        command=SubmitPublicSourceV1(
            requested_url="https://api.ashbyhq.com/posting-api/job-board/acme",
            company_name="Acme GmbH",
            company_domain="acme.example",
            idempotency_key=key,
            public_source_confirmed=True,
        ),
        actor=user,
        policy=settings.RUNTIME_SETTINGS.fetch,
        resolver=public_resolver,
    )


def poll_ashby(user: User, key: str, body: bytes, tmp_path: object) -> TaskOutbox:
    submission = submit_ashby(user, key)
    assert submission.pipeline_run is not None
    with override_settings(MEDIA_ROOT=tmp_path):
        execute_source_fetch(
            build_envelope(TaskOutbox.objects.get(pipeline_run=submission.pipeline_run)),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=FixtureFetcher(body),
        )
        parse_outbox = (
            TaskOutbox.objects.filter(command_type=JOBS_PARSE_COMMAND_TYPE)
            .order_by("-created_at")
            .first()
        )
        assert parse_outbox is not None
        execute_source_parse(build_envelope(parse_outbox))
    return parse_outbox


@pytest.mark.django_db
def test_changed_fetch_queues_and_executes_durable_normalization(tmp_path) -> None:
    user = User.objects.create_user(username="job-normalizer")
    submission = submit_ashby(user, "jobs.parse:success")
    assert submission.pipeline_run is not None
    source_outbox = TaskOutbox.objects.get(pipeline_run=submission.pipeline_run)
    source_envelope = build_envelope(source_outbox)

    with override_settings(MEDIA_ROOT=tmp_path):
        execute_source_fetch(
            source_envelope,
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=FixtureFetcher(ASHBY_FIXTURE.read_bytes()),
        )
        parse_outbox = TaskOutbox.objects.get(command_type=JOBS_PARSE_COMMAND_TYPE)
        assert parse_outbox.pipeline_run.pipeline_name == "jobs.normalization"
        execute_source_parse(build_envelope(parse_outbox))

    posting = JobPosting.objects.select_related("current_snapshot").get()
    parse_attempt = ConnectorParseAttempt.objects.get()
    parse_outbox.pipeline_run.refresh_from_db()
    assert parse_attempt.status == ParseStatus.SUCCEEDED
    assert parse_attempt.connector_key == "ashby"
    assert parse_attempt.posting_count == 1
    assert parse_outbox.pipeline_run.status == PipelineStatus.COMPLETE
    assert posting.title == "Director of Brand"
    assert posting.company.name == "Acme GmbH"
    assert posting.current_snapshot is not None
    assert posting.current_snapshot.description_text.startswith("Lead brand strategy")
    assert JobPostingSnapshot.objects.count() == 1
    assert JobLocation.objects.count() == 2
    assert PostingObservation.objects.count() == 1
    assert AuditEvent.objects.filter(action="jobs.source_snapshot_parse_queued").exists()
    assert AuditEvent.objects.filter(action="jobs.source_snapshot_normalized").exists()

    execute_source_parse(build_envelope(parse_outbox))
    assert JobPosting.objects.count() == 1
    assert JobPostingSnapshot.objects.count() == 1
    assert PostingObservation.objects.count() == 1


@pytest.mark.django_db
def test_unsupported_content_fails_visibly_without_creating_posting(tmp_path) -> None:
    user = User.objects.create_user(username="job-invalid")
    submission = submit_ashby(user, "jobs.parse:invalid")
    assert submission.pipeline_run is not None
    source_outbox = TaskOutbox.objects.get(pipeline_run=submission.pipeline_run)
    with override_settings(MEDIA_ROOT=tmp_path):
        execute_source_fetch(
            build_envelope(source_outbox),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=FixtureFetcher(b'{"apiVersion":"2","jobs":[]}', "application/json"),
        )
        parse_outbox = TaskOutbox.objects.get(command_type=JOBS_PARSE_COMMAND_TYPE)
        execute_source_parse(build_envelope(parse_outbox))

    attempt = ConnectorParseAttempt.objects.get()
    assert attempt.status == ParseStatus.INVALID_SCHEMA
    assert attempt.error_code == "ASHBY_SCHEMA"
    assert attempt.safe_error_message
    assert JobPosting.objects.count() == 0
    submission.endpoint.refresh_from_db()  # type: ignore[union-attr]
    assert submission.endpoint.status == EndpointStatus.DEGRADED  # type: ignore[union-attr]


@pytest.mark.django_db
def test_identical_source_body_reuses_snapshot_but_records_each_successful_poll(tmp_path) -> None:
    user = User.objects.create_user(username="job-noop")
    submission = submit_ashby(user, "jobs.parse:noop")
    assert submission.pipeline_run is not None
    with override_settings(MEDIA_ROOT=tmp_path):
        execute_source_fetch(
            build_envelope(TaskOutbox.objects.get(pipeline_run=submission.pipeline_run)),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=FixtureFetcher(ASHBY_FIXTURE.read_bytes()),
        )
        second_submission = submit_ashby(user, "jobs.parse:noop-second")
        assert second_submission.pipeline_run is not None
        execute_source_fetch(
            build_envelope(TaskOutbox.objects.get(pipeline_run=second_submission.pipeline_run)),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=FixtureFetcher(ASHBY_FIXTURE.read_bytes()),
        )

    assert SourceSnapshot.objects.count() == 1
    assert TaskOutbox.objects.filter(command_type=JOBS_PARSE_COMMAND_TYPE).count() == 2


@pytest.mark.django_db
def test_created_cosmetic_and_material_change_events_are_classified(tmp_path) -> None:
    user = User.objects.create_user(username="job-changes")
    initial = json.loads(ASHBY_FIXTURE.read_text())
    cosmetic = json.loads(ASHBY_FIXTURE.read_text())
    cosmetic["jobs"][0]["publishedAt"] = "2026-08-04T09:30:00Z"
    material = json.loads(json.dumps(cosmetic))
    material["jobs"][0]["title"] = "Vice President of Brand"

    poll_ashby(user, "jobs.changes:initial", json.dumps(initial).encode(), tmp_path)
    poll_ashby(user, "jobs.changes:cosmetic", json.dumps(cosmetic).encode(), tmp_path)
    poll_ashby(user, "jobs.changes:material", json.dumps(material).encode(), tmp_path)

    posting = JobPosting.objects.get()
    events = list(posting.change_events.order_by("occurred_at", "created_at"))
    assert [event.change_type for event in events] == [
        PostingChangeType.CREATED,
        PostingChangeType.COSMETIC,
        PostingChangeType.MATERIAL,
    ]
    assert events[1].changed_fields == ["metadata.published_at"]
    assert events[2].changed_fields == ["title"]
    assert JobPostingSnapshot.objects.count() == 3
    assert PostingObservation.objects.count() == 3


@pytest.mark.django_db
def test_complete_poll_absence_closes_after_threshold_and_reappearance_reopens(tmp_path) -> None:
    user = User.objects.create_user(username="job-lifecycle")
    present = json.loads(ASHBY_FIXTURE.read_text())
    empty = {"apiVersion": "1", "jobs": []}

    poll_ashby(user, "jobs.lifecycle:present", json.dumps(present).encode(), tmp_path)
    posting = JobPosting.objects.get()

    poll_ashby(user, "jobs.lifecycle:missing-one", json.dumps(empty).encode(), tmp_path)
    posting.refresh_from_db()
    assert posting.lifecycle_status == PostingLifecycle.OPEN
    assert posting.successful_absence_count == 1

    poll_ashby(user, "jobs.lifecycle:missing-two", json.dumps(empty).encode(), tmp_path)
    posting.refresh_from_db()
    assert posting.lifecycle_status == PostingLifecycle.CLOSED
    assert posting.successful_absence_count == 2
    assert posting.closure_reason == "consecutive_absence"
    assert posting.closed_at is not None

    poll_ashby(user, "jobs.lifecycle:reappeared", json.dumps(present).encode(), tmp_path)
    posting.refresh_from_db()
    assert posting.lifecycle_status == PostingLifecycle.OPEN
    assert posting.successful_absence_count == 0
    assert posting.closure_reason == ""
    assert posting.closed_at is None
    assert list(posting.change_events.values_list("change_type", flat=True)) == [
        PostingChangeType.REOPENED,
        PostingChangeType.CLOSED,
        PostingChangeType.CREATED,
    ]
    assert PostingObservation.objects.filter(state="missing").count() == 2
    assert AuditEvent.objects.filter(action="jobs.posting_closed").count() == 1
    assert AuditEvent.objects.filter(action="jobs.posting_open").count() == 1


@pytest.mark.django_db
def test_failed_or_partial_parse_does_not_count_as_absence(tmp_path) -> None:
    user = User.objects.create_user(username="job-no-false-close")
    poll_ashby(user, "jobs.failure:present", ASHBY_FIXTURE.read_bytes(), tmp_path)
    posting = JobPosting.objects.get()

    poll_ashby(
        user,
        "jobs.failure:invalid",
        b'{"apiVersion":"2","jobs":[]}',
        tmp_path,
    )

    posting.refresh_from_db()
    assert posting.lifecycle_status == PostingLifecycle.OPEN
    assert posting.successful_absence_count == 0
    assert PostingObservation.objects.filter(posting=posting).count() == 1


@pytest.mark.django_db
def test_exact_canonical_url_duplicate_is_linked_without_merging(tmp_path) -> None:
    user = User.objects.create_user(username="job-duplicates")
    poll_ashby(user, "jobs.duplicates:initial", ASHBY_FIXTURE.read_bytes(), tmp_path)
    original = JobPosting.objects.select_related("current_snapshot").get()
    original_snapshot = original.current_snapshot
    assert original_snapshot is not None
    secondary = JobPosting.objects.create(
        company=original.company,
        primary_source_endpoint=original.primary_source_endpoint,
        provider_type=original.provider_type,
        external_posting_id="alternate-provider-identity",
        canonical_url=original.canonical_url,
        apply_url=f"{original.apply_url}?variant=alternate",
        source_url=original.source_url,
        title="Director, Brand",
        normalized_title="director, brand",
        department=original.department,
        team=original.team,
        employment_type=original.employment_type,
        language=original.language,
        first_seen_at=original.first_seen_at,
        last_seen_at=original.last_seen_at,
    )
    secondary_snapshot = JobPostingSnapshot.objects.create(
        posting=secondary,
        source_snapshot=original_snapshot.source_snapshot,
        parse_run=original_snapshot.parse_run,
        connector_key=original_snapshot.connector_key,
        connector_version=original_snapshot.connector_version,
        normalizer_version=original_snapshot.normalizer_version,
        retrieved_at=original_snapshot.retrieved_at,
        title=secondary.title,
        description_text=original_snapshot.description_text,
        structured_sections=original_snapshot.structured_sections,
        metadata=original_snapshot.metadata,
        locations_payload=original_snapshot.locations_payload,
        full_hash="a" * 64,
        semantic_hash=original_snapshot.semantic_hash,
    )
    secondary.current_snapshot = secondary_snapshot
    secondary.save(update_fields=("current_snapshot", "updated_at"))

    _link_exact_duplicates(secondary)

    relationship = DuplicateRelationship.objects.get()
    assert relationship.method == "canonical_url"
    assert {relationship.primary_posting_id, relationship.secondary_posting_id} == {
        original.pk,
        secondary.pk,
    }
    assert JobPosting.objects.count() == 2


@pytest.mark.django_db
def test_parse_envelope_replay_does_not_duplicate_change_effects(tmp_path) -> None:
    user = User.objects.create_user(username="job-change-replay")
    outbox = poll_ashby(user, "jobs.replay:initial", ASHBY_FIXTURE.read_bytes(), tmp_path)

    execute_source_parse(build_envelope(outbox))

    assert JobPosting.objects.count() == 1
    assert PostingObservation.objects.count() == 1
    assert PostingChangeEvent.objects.count() == 1
