import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.test import override_settings

from apps.companies.models import Company, CompanyMergeReview, CompanyStatus
from apps.operations.commands import SOURCE_FETCH_COMMAND_TYPE
from apps.operations.models import AuditEvent, PipelineStatus, TaskOutbox
from apps.operations.outbox import build_envelope
from apps.sources.contracts import SafeFetchResultV1, SubmitPublicSourceV1
from apps.sources.http import SafeFetchError
from apps.sources.models import (
    CandidateStatus,
    FetchAttempt,
    FetchStatus,
    SourceArtifact,
    SourceEndpoint,
    SourceSnapshot,
)
from apps.sources.services import (
    RetryableFetchError,
    execute_source_fetch,
    mark_fetch_exhausted,
    submit_public_source,
)

PUBLIC_IP = "93.184.216.34"


def public_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
    return (PUBLIC_IP,)


def submit(
    user: User,
    key: str,
    *,
    url: str = "https://example.com/jobs",
    company_name: str | None = "Example GmbH",
    company_domain: str | None = "example.com",
):
    return submit_public_source(
        command=SubmitPublicSourceV1(
            requested_url=url,
            company_name=company_name,
            company_domain=company_domain,
            idempotency_key=key,
            request_id=uuid4(),
            public_source_confirmed=True,
        ),
        actor=user,
        policy=settings.RUNTIME_SETTINGS.fetch,
        resolver=public_resolver,
    )


class StaticFetcher:
    def __init__(self, body: bytes = b"<html><h1>Public role</h1></html>") -> None:
        self.body = body
        self.calls = 0

    def fetch(self, requested_url: str, *, etag: str = "", last_modified: str = ""):
        self.calls += 1
        return SafeFetchResultV1(
            requested_url=requested_url,
            final_url=requested_url,
            status_code=200,
            retrieved_at_iso=datetime.now(UTC).isoformat(),
            content_type="text/html",
            encoding="utf-8",
            headers_filtered={"etag": '"fixture-1"'},
            body=self.body,
            body_sha256=hashlib.sha256(self.body).hexdigest(),
            body_size_bytes=len(self.body),
            elapsed_ms=12,
            redirect_chain=[],
        )


class FailingFetcher:
    def fetch(self, _requested_url: str, *, etag: str = "", last_modified: str = ""):
        raise SafeFetchError(
            "FETCH_HTTP_STATUS",
            "The public source returned HTTP 503.",
            retryable=True,
            status_code=503,
        )


@pytest.mark.django_db
def test_submission_atomically_creates_company_source_run_outbox_and_audit() -> None:
    user = User.objects.create_user(username="source-submitter")

    result = submit(user, "sources.manual:atomic")

    assert result.accepted is True
    assert result.created is True
    assert result.endpoint is not None
    assert result.pipeline_run is not None
    assert result.candidate.status == CandidateStatus.FETCH_QUEUED
    assert result.endpoint.company is not None
    assert result.endpoint.company.status == CompanyStatus.PROVISIONAL
    assert result.endpoint.company.domains.get().hostname_ascii == "example.com"
    assert result.pipeline_run.status == PipelineStatus.QUEUED
    outbox = TaskOutbox.objects.get(pipeline_run=result.pipeline_run)
    assert outbox.command_type == SOURCE_FETCH_COMMAND_TYPE
    assert outbox.payload == {
        "pipeline_run_id": str(result.pipeline_run.pk),
        "object_id": str(result.endpoint.pk),
    }
    assert AuditEvent.objects.filter(action="sources.public_source_queued").count() == 1


@pytest.mark.django_db
def test_submission_is_idempotent_and_unsafe_target_never_creates_outbox() -> None:
    user = User.objects.create_user(username="source-idempotency")

    first = submit(user, "sources.manual:idempotent")
    second = submit(user, "sources.manual:idempotent")
    unsafe = submit_public_source(
        command=SubmitPublicSourceV1(
            requested_url="https://127.0.0.1/admin",
            idempotency_key="sources.manual:unsafe",
            request_id=uuid4(),
            public_source_confirmed=True,
        ),
        actor=user,
        policy=settings.RUNTIME_SETTINGS.fetch,
    )

    assert second.created is False
    assert first.candidate.pk == second.candidate.pk
    assert SourceEndpoint.objects.count() == 1
    assert TaskOutbox.objects.count() == 1
    assert unsafe.accepted is False
    assert unsafe.candidate.status == CandidateStatus.UNSAFE
    assert unsafe.pipeline_run is None
    assert "prohibited network" in unsafe.candidate.rejection_reason
    assert AuditEvent.objects.filter(action="sources.public_source_rejected").count() == 1


@pytest.mark.django_db
def test_ambiguous_unverified_identity_creates_merge_review_instead_of_auto_merge() -> None:
    user = User.objects.create_user(username="identity-review")

    first = submit(user, "sources.manual:identity-1")
    second = submit(
        user,
        "sources.manual:identity-2",
        url="https://example.com/careers",
    )

    assert first.endpoint is not None
    assert second.endpoint is not None
    assert first.endpoint.company_id != second.endpoint.company_id
    assert Company.objects.count() == 2
    review = CompanyMergeReview.objects.get()
    assert review.match_method == "shared_unverified_domain"
    assert review.state == "open"
    second.endpoint.company.refresh_from_db()  # type: ignore[union-attr]
    assert second.endpoint.company.status == CompanyStatus.MERGE_REVIEW  # type: ignore[union-attr]


@pytest.mark.django_db
def test_fetch_persists_body_in_storage_and_metadata_in_postgres(tmp_path) -> None:
    user = User.objects.create_user(username="source-fetch")
    result = submit(user, "sources.manual:fetch")
    assert result.pipeline_run is not None
    fetcher = StaticFetcher()
    envelope = build_envelope(TaskOutbox.objects.get(pipeline_run=result.pipeline_run))

    with override_settings(MEDIA_ROOT=tmp_path):
        attempt = execute_source_fetch(
            envelope,
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=fetcher,
        )
        artifact = SourceArtifact.objects.get()
        assert default_storage.open(artifact.storage_key, "rb").read() == fetcher.body

    result.candidate.refresh_from_db()
    result.pipeline_run.refresh_from_db()
    assert attempt.status == FetchStatus.FETCHED
    assert result.candidate.status == CandidateStatus.REGISTERED
    assert result.pipeline_run.status == PipelineStatus.COMPLETE
    assert SourceSnapshot.objects.get().body_sha256 == artifact.sha256
    assert FetchAttempt.objects.count() == 1
    assert AuditEvent.objects.filter(action="sources.public_source_fetched").count() == 1

    duplicate = execute_source_fetch(
        envelope,
        policy=settings.RUNTIME_SETTINGS.fetch,
        fetcher=fetcher,
    )
    assert duplicate.pk == attempt.pk
    assert fetcher.calls == 1
    assert SourceSnapshot.objects.count() == 1


@pytest.mark.django_db
def test_retryable_fetch_failure_is_durable_and_later_attempt_can_succeed(tmp_path) -> None:
    user = User.objects.create_user(username="fetch-retry")
    result = submit(user, "sources.manual:retry")
    assert result.pipeline_run is not None
    assert result.endpoint is not None
    envelope = build_envelope(TaskOutbox.objects.get(pipeline_run=result.pipeline_run))

    with pytest.raises(RetryableFetchError):
        execute_source_fetch(
            envelope,
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=FailingFetcher(),
        )

    first_attempt = FetchAttempt.objects.get()
    result.pipeline_run.refresh_from_db()
    assert first_attempt.status == FetchStatus.FAILED
    assert first_attempt.retryable is True
    assert first_attempt.http_status == 503
    assert result.pipeline_run.status == PipelineStatus.QUEUED

    with override_settings(MEDIA_ROOT=tmp_path):
        recovered = execute_source_fetch(
            envelope,
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=StaticFetcher(),
        )
    assert recovered.attempt_count == 2
    assert recovered.status == FetchStatus.FETCHED
    assert FetchAttempt.objects.count() == 2


@pytest.mark.django_db
def test_source_records_are_application_immutable(
    tmp_path,
) -> None:
    user = User.objects.create_user(username="fetch-exhausted")
    result = submit(user, "sources.manual:exhausted")
    assert result.pipeline_run is not None
    envelope = build_envelope(TaskOutbox.objects.get(pipeline_run=result.pipeline_run))
    with override_settings(MEDIA_ROOT=tmp_path):
        execute_source_fetch(
            envelope,
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=StaticFetcher(),
        )
    artifact = SourceArtifact.objects.get()
    snapshot = SourceSnapshot.objects.get()

    artifact.content_type = "text/plain"
    with pytest.raises(ValidationError, match="immutable"):
        artifact.save()
    with pytest.raises(TypeError, match=r"[Ii]mmutable"):
        SourceArtifact.objects.filter(pk=artifact.pk).update(content_type="text/plain")
    with pytest.raises(TypeError, match=r"[Ii]mmutable"):
        snapshot.delete()


@pytest.mark.django_db
def test_mark_fetch_exhausted_updates_run_candidate_endpoint_and_audit() -> None:
    user = User.objects.create_user(username="fetch-bounded")
    result = submit(user, "sources.manual:bounded")
    assert result.pipeline_run is not None
    assert result.endpoint is not None

    mark_fetch_exhausted(pipeline_run_id=result.pipeline_run.pk)

    result.pipeline_run.refresh_from_db()
    result.candidate.refresh_from_db()
    result.endpoint.refresh_from_db()
    assert result.pipeline_run.status == PipelineStatus.FAILED
    assert result.pipeline_run.last_error_code == "FETCH_RETRIES_EXHAUSTED"
    assert result.candidate.status == CandidateStatus.REJECTED
    assert result.endpoint.status == "degraded"
    assert AuditEvent.objects.filter(action="sources.public_source_fetch_exhausted").exists()
