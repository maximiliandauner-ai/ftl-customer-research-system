from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from django.contrib.auth.models import User as DjangoUser
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import TeamRole
from apps.companies.models import (
    AliasVerificationStatus,
    Company,
    CompanyAlias,
    CompanyDomain,
    CompanyMergeReview,
    CompanyStatus,
    DomainVerificationStatus,
    MergeReviewState,
)
from apps.operations.commands import SOURCE_FETCH_COMMAND_TYPE
from apps.operations.contracts import TargetCommandPayloadV1, TaskEnvelopeV2
from apps.operations.models import (
    ActorType,
    AuditEvent,
    PipelineRun,
    PipelineStatus,
    PipelineStepRun,
    PipelineTrigger,
    StepStatus,
    TaskOutbox,
)
from apps.sources.contracts import SafeFetchResultV1, SubmitPublicSourceV1
from apps.sources.http import SafeFetchError, SafeHttpFetcher
from apps.sources.models import (
    CandidateOrigin,
    CandidateStatus,
    EndpointStatus,
    FetchAttempt,
    FetchStatus,
    NetworkPolicy,
    ProviderType,
    SourceArtifact,
    SourceCandidate,
    SourceEndpoint,
    SourceSnapshot,
)
from apps.sources.policy import (
    Resolver,
    SourcePolicyError,
    canonicalize_url,
    normalize_company_name,
    normalize_hostname,
    redact_url,
    registrable_domain,
    system_resolver,
    validate_target,
)
from config.runtime import FetchPolicySettings


class Fetcher(Protocol):
    def fetch(
        self,
        requested_url: str,
        *,
        etag: str = "",
        last_modified: str = "",
    ) -> SafeFetchResultV1: ...


class RetryableFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceSubmissionResult:
    candidate: SourceCandidate
    endpoint: SourceEndpoint | None
    pipeline_run: PipelineRun | None
    accepted: bool
    created: bool


@dataclass(frozen=True)
class FetchStart:
    attempt: FetchAttempt
    endpoint: SourceEndpoint
    pipeline_run: PipelineRun
    candidate: SourceCandidate
    should_fetch: bool


def _actor_role_id(user: DjangoUser | None) -> UUID | None:
    if user is None:
        return None
    return TeamRole.objects.filter(user=user).values_list("pk", flat=True).first()


def _candidate_rejected(
    *,
    command: SubmitPublicSourceV1,
    actor: DjangoUser | None,
    error: SourcePolicyError,
    policy: FetchPolicySettings,
    origin: str,
) -> SourceSubmissionResult:
    try:
        canonical = canonicalize_url(command.requested_url, policy)
        canonical_url = canonical.canonical
        url_hash = canonical.sha256
        original = canonical.original_redacted
    except SourcePolicyError:
        canonical_url = ""
        url_hash = ""
        original = redact_url(command.requested_url)
    with transaction.atomic():
        candidate, created = SourceCandidate.objects.get_or_create(
            idempotency_key=command.idempotency_key,
            defaults={
                "origin": origin,
                "url_original": original,
                "url_canonical": canonical_url,
                "url_sha256": url_hash,
                "company_name_hint": command.company_name or "",
                "company_domain_hint": command.company_domain or "",
                "status": CandidateStatus.UNSAFE,
                "rejection_reason": error.safe_message,
                "submitted_by": actor,
                "request_id": command.request_id,
            },
        )
        if created:
            AuditEvent.objects.create(
                actor_type=ActorType.USER if actor is not None else ActorType.SYSTEM,
                actor_id=_actor_role_id(actor),
                action="sources.public_source_rejected",
                object_type="source_candidate",
                object_id=candidate.pk,
                after_summary={"status": CandidateStatus.UNSAFE, "error_code": error.code},
                reason_key="network_policy",
                request_id=command.request_id,
            )
    return SourceSubmissionResult(
        candidate=candidate,
        endpoint=None,
        pipeline_run=None,
        accepted=False,
        created=created,
    )


def _resolve_company_hint(
    *,
    company_name: str | None,
    company_domain: str | None,
    source_url: str,
) -> Company | None:
    if not company_name:
        return None
    normalized_name = normalize_company_name(company_name)
    reviewed_alias = (
        CompanyAlias.objects.select_related("company")
        .filter(
            normalized_alias=normalized_name,
            verification_status__in=(
                AliasVerificationStatus.SOURCE_CONFIRMED,
                AliasVerificationStatus.HUMAN_VERIFIED,
            ),
        )
        .order_by("company_id")
        .first()
    )
    hostname_ascii = ""
    hostname_unicode = ""
    possible_companies: dict[UUID, Company] = {
        company.pk: company
        for company in Company.objects.filter(normalized_name=normalized_name).order_by("pk")
    }
    if company_domain:
        hostname_ascii, hostname_unicode = normalize_hostname(company_domain)
        domain_matches = list(
            CompanyDomain.objects.select_related("company")
            .filter(hostname_ascii=hostname_ascii)
            .order_by("company_id")
        )
        possible_companies.update(
            {domain_match.company_id: domain_match.company for domain_match in domain_matches}
        )
        confirmed = [
            domain_match
            for domain_match in domain_matches
            if domain_match.verification_status
            in (
                DomainVerificationStatus.SOURCE_CONFIRMED,
                DomainVerificationStatus.HUMAN_VERIFIED,
            )
        ]
        if len(confirmed) == 1:
            company = confirmed[0].company
            if company.normalized_name != normalized_name:
                CompanyAlias.objects.get_or_create(
                    company=company,
                    normalized_alias=normalized_name,
                    defaults={
                        "alias": company_name,
                        "verification_status": AliasVerificationStatus.UNVERIFIED,
                        "verification_source_url": source_url,
                    },
                )
            return company
    if reviewed_alias is not None:
        return reviewed_alias.company
    company = Company.objects.create(
        name=company_name,
        normalized_name=normalized_name,
        status=(CompanyStatus.MERGE_REVIEW if possible_companies else CompanyStatus.PROVISIONAL),
    )
    if hostname_ascii:
        now = timezone.now()
        CompanyDomain.objects.create(
            company=company,
            hostname_ascii=hostname_ascii,
            hostname_unicode=hostname_unicode,
            registrable_domain=registrable_domain(hostname_ascii),
            is_primary=True,
            verification_status=DomainVerificationStatus.UNVERIFIED,
            verification_source_url=source_url,
            first_seen_at=now,
            last_seen_at=now,
        )
    for possible_company in possible_companies.values():
        left_id, right_id = sorted((company.pk, possible_company.pk), key=str)
        CompanyMergeReview.objects.get_or_create(
            left_company_id=left_id,
            right_company_id=right_id,
            state=MergeReviewState.OPEN,
            defaults={
                "match_method": (
                    "shared_unverified_domain" if hostname_ascii else "exact_unreviewed_name"
                ),
                "confidence": Decimal("0.650") if hostname_ascii else Decimal("0.500"),
                "note": "Created from a source hint; human identity resolution is required.",
            },
        )
    return company


def submit_public_source(
    *,
    command: SubmitPublicSourceV1,
    actor: DjangoUser | None,
    policy: FetchPolicySettings,
    resolver: Resolver = system_resolver,
    origin: str = CandidateOrigin.MANUAL,
    trigger: str = PipelineTrigger.MANUAL,
) -> SourceSubmissionResult:
    existing = (
        SourceCandidate.objects.select_related("registered_endpoint", "pipeline_run")
        .filter(idempotency_key=command.idempotency_key)
        .first()
    )
    if existing is not None:
        return SourceSubmissionResult(
            candidate=existing,
            endpoint=existing.registered_endpoint,
            pipeline_run=existing.pipeline_run,
            accepted=existing.status not in (CandidateStatus.UNSAFE, CandidateStatus.REJECTED),
            created=False,
        )
    try:
        target = validate_target(command.requested_url, policy, resolver=resolver)
    except SourcePolicyError as exc:
        return _candidate_rejected(
            command=command,
            actor=actor,
            error=exc,
            policy=policy,
            origin=origin,
        )
    with transaction.atomic():
        candidate = SourceCandidate.objects.create(
            origin=origin,
            url_original=target.url.original_redacted,
            url_canonical=target.url.canonical,
            url_sha256=target.url.sha256,
            company_name_hint=command.company_name or "",
            company_domain_hint=command.company_domain or "",
            status=CandidateStatus.FETCH_QUEUED,
            idempotency_key=command.idempotency_key,
            submitted_by=actor,
            request_id=command.request_id,
        )
        endpoint = (
            SourceEndpoint.objects.select_for_update()
            .filter(base_url_sha256=target.url.sha256)
            .first()
        )
        if endpoint is not None and endpoint.status == EndpointStatus.BLOCKED:
            candidate.status = CandidateStatus.REJECTED
            candidate.rejection_reason = "This source endpoint is blocked by an operator policy."
            candidate.registered_endpoint = endpoint
            candidate.save(update_fields=("status", "rejection_reason", "registered_endpoint"))
            AuditEvent.objects.create(
                actor_type=ActorType.USER if actor is not None else ActorType.SYSTEM,
                actor_id=_actor_role_id(actor),
                action="sources.public_source_rejected",
                object_type="source_candidate",
                object_id=candidate.pk,
                after_summary={"status": CandidateStatus.REJECTED, "endpoint_id": str(endpoint.pk)},
                reason_key="endpoint_blocked",
                request_id=command.request_id,
            )
            return SourceSubmissionResult(candidate, endpoint, None, False, True)
        if endpoint is None:
            company = _resolve_company_hint(
                company_name=command.company_name,
                company_domain=command.company_domain,
                source_url=target.url.canonical,
            )
            endpoint = SourceEndpoint.objects.create(
                company=company,
                candidate=candidate,
                provider_type=ProviderType.UNKNOWN,
                base_url_original=target.url.original_redacted,
                base_url_canonical=target.url.canonical,
                base_url_sha256=target.url.sha256,
            )
        run = PipelineRun.objects.create(
            pipeline_name="source.ingestion",
            stage="fetch_queued",
            status=PipelineStatus.QUEUED,
            trigger=trigger,
            requested_by=actor,
            idempotency_key=f"sources.ingest:{command.idempotency_key}",
            request_id=command.request_id,
            object_type="source_endpoint",
            object_id=endpoint.pk,
            heartbeat_at=timezone.now(),
            input_count=1,
            policy_versions={"source_submission": "1.0", "fetch_policy": "1.0"},
            context={"candidate_id": str(candidate.pk)},
        )
        candidate.registered_endpoint = endpoint
        candidate.pipeline_run = run
        candidate.save(update_fields=("registered_endpoint", "pipeline_run"))
        payload = TargetCommandPayloadV1(pipeline_run_id=run.pk, object_id=endpoint.pk)
        outbox = TaskOutbox(
            command_type=SOURCE_FETCH_COMMAND_TYPE,
            payload=payload.model_dump(mode="json"),
            payload_schema_version="1.0",
            idempotency_key=f"sources.fetch:{command.idempotency_key}",
            pipeline_run=run,
            request_id=command.request_id,
        )
        outbox.full_clean()
        outbox.save()
        AuditEvent.objects.create(
            actor_type=ActorType.USER if actor is not None else ActorType.SYSTEM,
            actor_id=_actor_role_id(actor),
            action="sources.public_source_queued",
            object_type="source_candidate",
            object_id=candidate.pk,
            after_summary={
                "status": CandidateStatus.FETCH_QUEUED,
                "endpoint_id": str(endpoint.pk),
                "outbox_id": str(outbox.pk),
            },
            reason_key=(
                "discovered_public_source"
                if origin == CandidateOrigin.DISCOVERY
                else "manual_public_source"
            ),
            request_id=command.request_id,
            pipeline_run=run,
        )
    return SourceSubmissionResult(candidate, endpoint, run, True, True)


def queue_registered_endpoint(
    *,
    endpoint: SourceEndpoint,
    idempotency_key: str,
    trigger: str = PipelineTrigger.SCHEDULED,
    actor: DjangoUser | None = None,
) -> SourceSubmissionResult:
    existing = (
        SourceCandidate.objects.select_related("registered_endpoint", "pipeline_run")
        .filter(idempotency_key=idempotency_key)
        .first()
    )
    if existing is not None:
        return SourceSubmissionResult(
            candidate=existing,
            endpoint=existing.registered_endpoint,
            pipeline_run=existing.pipeline_run,
            accepted=True,
            created=False,
        )
    with transaction.atomic():
        candidate = SourceCandidate.objects.create(
            origin=CandidateOrigin.DISCOVERY,
            url_original=endpoint.base_url_original,
            url_canonical=endpoint.base_url_canonical,
            url_sha256=endpoint.base_url_sha256,
            company_name_hint=endpoint.company.name if endpoint.company else "",
            status=CandidateStatus.FETCH_QUEUED,
            idempotency_key=idempotency_key,
            submitted_by=actor,
            registered_endpoint=endpoint,
        )
        run = PipelineRun.objects.create(
            pipeline_name="source.ingestion",
            stage="fetch_queued",
            status=PipelineStatus.QUEUED,
            trigger=trigger,
            requested_by=actor,
            idempotency_key=f"sources.ingest:{idempotency_key}",
            object_type="source_endpoint",
            object_id=endpoint.pk,
            heartbeat_at=timezone.now(),
            input_count=1,
            policy_versions={"known_endpoint_poll": "1.0", "fetch_policy": "1.0"},
            context={"candidate_id": str(candidate.pk)},
        )
        candidate.pipeline_run = run
        candidate.save(update_fields=("pipeline_run",))
        payload = TargetCommandPayloadV1(pipeline_run_id=run.pk, object_id=endpoint.pk)
        outbox = TaskOutbox(
            command_type=SOURCE_FETCH_COMMAND_TYPE,
            payload=payload.model_dump(mode="json"),
            payload_schema_version="1.0",
            idempotency_key=f"sources.fetch:{idempotency_key}",
            pipeline_run=run,
        )
        outbox.full_clean()
        outbox.save()
        AuditEvent.objects.create(
            actor_type=ActorType.USER if actor is not None else ActorType.SYSTEM,
            actor_id=_actor_role_id(actor),
            action="sources.known_endpoint_queued",
            object_type="source_endpoint",
            object_id=endpoint.pk,
            after_summary={"pipeline_run_id": str(run.pk), "outbox_id": str(outbox.pk)},
            reason_key="scheduled_known_endpoint_poll",
            pipeline_run=run,
        )
    return SourceSubmissionResult(candidate, endpoint, run, True, True)


def _begin_fetch(
    envelope: TaskEnvelopeV2,
    *,
    recover_started: bool,
) -> FetchStart:
    if envelope.command_type != SOURCE_FETCH_COMMAND_TYPE:
        raise ValueError("Unsupported source-fetch command type.")
    with transaction.atomic():
        run = PipelineRun.objects.select_for_update().get(pk=envelope.pipeline_run_id)
        endpoint = SourceEndpoint.objects.select_for_update().get(pk=envelope.object_id)
        outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=run)
        if outbox.idempotency_key != envelope.idempotency_key:
            raise ValueError("Envelope idempotency does not match the source outbox command.")
        candidate = SourceCandidate.objects.select_for_update().get(pipeline_run=run)
        last_attempt = (
            FetchAttempt.objects.filter(pipeline_run=run).order_by("-attempt_count").first()
        )
        if last_attempt is not None and last_attempt.status in (
            FetchStatus.FETCHED,
            FetchStatus.NOT_MODIFIED,
        ):
            return FetchStart(last_attempt, endpoint, run, candidate, False)
        if last_attempt is not None and last_attempt.status == FetchStatus.STARTED:
            if not recover_started:
                return FetchStart(last_attempt, endpoint, run, candidate, False)
            last_attempt.status = FetchStatus.FAILED
            last_attempt.completed_at = timezone.now()
            last_attempt.retryable = True
            last_attempt.error_code = "FETCH_WORKER_INTERRUPTED"
            last_attempt.safe_error_message = "An interrupted fetch attempt was recovered."
            last_attempt.save(
                update_fields=(
                    "status",
                    "completed_at",
                    "retryable",
                    "error_code",
                    "safe_error_message",
                )
            )
        attempt_number = (last_attempt.attempt_count + 1) if last_attempt is not None else 1
        now = timezone.now()
        attempt = FetchAttempt.objects.create(
            source_endpoint=endpoint,
            pipeline_run=run,
            idempotency_key=f"sources.fetch:{run.pk}:attempt:{attempt_number}",
            requested_url=endpoint.base_url_canonical,
            started_at=now,
            attempt_count=attempt_number,
            robots_policy=endpoint.robots_policy,
        )
        step_key = f"sources.fetch:{run.pk}:effect"
        step = PipelineStepRun.objects.filter(idempotency_key=step_key).first()
        if step is None:
            PipelineStepRun.objects.create(
                pipeline_run=run,
                stage="source_fetch",
                status=StepStatus.RUNNING,
                idempotency_key=step_key,
                attempt=attempt_number,
                started_at=now,
                heartbeat_at=now,
                input_ids={"source_endpoint_id": str(endpoint.pk)},
            )
        else:
            step.status = StepStatus.RUNNING
            step.attempt = attempt_number
            step.started_at = now
            step.heartbeat_at = now
            step.completed_at = None
            step.last_error_code = ""
            step.last_error_message = ""
            step.save(
                update_fields=(
                    "status",
                    "attempt",
                    "started_at",
                    "heartbeat_at",
                    "completed_at",
                    "last_error_code",
                    "last_error_message",
                    "updated_at",
                )
            )
        run.status = PipelineStatus.RUNNING
        run.stage = "source_fetch"
        run.started_at = run.started_at or now
        run.heartbeat_at = now
        run.attempts += 1
        run.row_version += 1
        run.save(
            update_fields=(
                "status",
                "stage",
                "started_at",
                "heartbeat_at",
                "attempts",
                "row_version",
                "updated_at",
            )
        )
        return FetchStart(attempt, endpoint, run, candidate, True)


def _parser_hint(content_type: str) -> str:
    if "json" in content_type:
        return "json"
    if "xml" in content_type:
        return "xml"
    if "html" in content_type:
        return "html"
    return "text"


def _artifact_key(endpoint_id: UUID, body_sha256: str) -> str:
    return f"sources/{endpoint_id}/{body_sha256[:2]}/{body_sha256}.bin"


def _persist_body(endpoint: SourceEndpoint, result: SafeFetchResultV1) -> str:
    storage_key = _artifact_key(endpoint.pk, result.body_sha256)
    if default_storage.exists(storage_key):
        if default_storage.size(storage_key) != result.body_size_bytes:
            raise OSError("An immutable artifact key exists with a different size.")
        return storage_key
    stored_key = default_storage.save(storage_key, ContentFile(result.body))
    if stored_key != storage_key:
        raise OSError("The storage backend did not preserve the immutable artifact key.")
    return storage_key


def _complete_fetch(start: FetchStart, result: SafeFetchResultV1, storage_key: str) -> None:
    retrieved_at = datetime.fromisoformat(result.retrieved_at_iso)
    with transaction.atomic():
        attempt = FetchAttempt.objects.select_for_update().get(pk=start.attempt.pk)
        if attempt.status != FetchStatus.STARTED:
            return
        endpoint = SourceEndpoint.objects.select_for_update().get(pk=start.endpoint.pk)
        run = PipelineRun.objects.select_for_update().get(pk=start.pipeline_run.pk)
        candidate = SourceCandidate.objects.select_for_update().get(pk=start.candidate.pk)
        step = PipelineStepRun.objects.select_for_update().get(
            idempotency_key=f"sources.fetch:{run.pk}:effect"
        )
        now = timezone.now()
        snapshot: SourceSnapshot | None = None
        artifact: SourceArtifact | None = None
        if result.status_code == 304:
            attempt.status = FetchStatus.NOT_MODIFIED
            snapshot = SourceSnapshot.objects.filter(source_endpoint=endpoint).first()
        else:
            artifact, _artifact_created = SourceArtifact.objects.get_or_create(
                source_endpoint=endpoint,
                sha256=result.body_sha256,
                defaults={
                    "storage_key": storage_key,
                    "size_bytes": result.body_size_bytes,
                    "content_type": result.content_type,
                    "encoding": result.encoding,
                    "retrieved_at": retrieved_at,
                },
            )
            snapshot = SourceSnapshot.objects.filter(
                source_endpoint=endpoint,
                body_sha256=result.body_sha256,
            ).first()
            if snapshot is None:
                snapshot = SourceSnapshot.objects.create(
                    source_endpoint=endpoint,
                    fetch_attempt=attempt,
                    artifact=artifact,
                    retrieved_at=retrieved_at,
                    body_sha256=result.body_sha256,
                    content_type=result.content_type,
                    encoding=result.encoding,
                    parser_hint=_parser_hint(result.content_type),
                )
            attempt.status = FetchStatus.FETCHED
        attempt.final_url = result.final_url
        attempt.network_policy = NetworkPolicy.ALLOWED
        attempt.http_status = result.status_code
        attempt.completed_at = now
        attempt.elapsed_ms = result.elapsed_ms
        attempt.redirect_chain = result.redirect_chain
        attempt.response_headers_filtered = result.headers_filtered
        attempt.body_sha256 = result.body_sha256 if result.status_code != 304 else ""
        attempt.body_size_bytes = result.body_size_bytes if result.status_code != 304 else None
        attempt.content_type = result.content_type
        attempt.encoding = result.encoding
        attempt.retryable = False
        attempt.error_code = ""
        attempt.safe_error_message = ""
        attempt.save(
            update_fields=(
                "status",
                "final_url",
                "network_policy",
                "http_status",
                "completed_at",
                "elapsed_ms",
                "redirect_chain",
                "response_headers_filtered",
                "body_sha256",
                "body_size_bytes",
                "content_type",
                "encoding",
                "retryable",
                "error_code",
                "safe_error_message",
            )
        )
        endpoint.etag = result.headers_filtered.get("etag", endpoint.etag)
        endpoint.last_modified = result.headers_filtered.get(
            "last-modified", endpoint.last_modified
        )
        endpoint.last_success_at = now
        endpoint.consecutive_failures = 0
        endpoint.status = EndpointStatus.ACTIVE
        endpoint.next_allowed_fetch_at = None
        endpoint.save(
            update_fields=(
                "etag",
                "last_modified",
                "last_success_at",
                "consecutive_failures",
                "status",
                "next_allowed_fetch_at",
                "updated_at",
            )
        )
        candidate.status = CandidateStatus.REGISTERED
        candidate.rejection_reason = ""
        candidate.save(update_fields=("status", "rejection_reason"))
        step.status = StepStatus.COMPLETE
        step.completed_at = now
        step.heartbeat_at = now
        step.output_ids = {
            "fetch_attempt_id": str(attempt.pk),
            "artifact_id": str(artifact.pk) if artifact else None,
            "source_snapshot_id": str(snapshot.pk) if snapshot else None,
        }
        step.save(
            update_fields=(
                "status",
                "completed_at",
                "heartbeat_at",
                "output_ids",
                "updated_at",
            )
        )
        run.status = PipelineStatus.COMPLETE
        run.stage = "source_fetch_complete"
        run.completed_at = now
        run.heartbeat_at = now
        run.output_count = 1
        run.last_error_code = ""
        run.last_error_message = ""
        run.row_version += 1
        run.save(
            update_fields=(
                "status",
                "stage",
                "completed_at",
                "heartbeat_at",
                "output_count",
                "last_error_code",
                "last_error_message",
                "row_version",
                "updated_at",
            )
        )
        AuditEvent.objects.create(
            actor_type=ActorType.SYSTEM,
            action="sources.public_source_fetched",
            object_type="source_endpoint",
            object_id=endpoint.pk,
            after_summary={
                "status": attempt.status,
                "fetch_attempt_id": str(attempt.pk),
                "artifact_id": str(artifact.pk) if artifact else None,
                "source_snapshot_id": str(snapshot.pk) if snapshot else None,
                "body_sha256": result.body_sha256 if artifact else None,
            },
            reason_key="safe_fetch_complete",
            request_id=run.request_id,
            pipeline_run=run,
        )
        if snapshot is not None:
            from apps.jobs.services import schedule_parse_for_snapshot

            parse_run, parse_outbox, _created = schedule_parse_for_snapshot(
                snapshot,
                source_run=run,
                fetch_attempt=attempt,
            )
            AuditEvent.objects.create(
                actor_type=ActorType.SYSTEM,
                action="jobs.source_snapshot_parse_queued",
                object_type="source_snapshot",
                object_id=snapshot.pk,
                after_summary={
                    "parse_run_id": str(parse_run.pk),
                    "outbox_id": str(parse_outbox.pk),
                },
                reason_key=(
                    "changed_source_snapshot"
                    if result.status_code != 304 and snapshot.fetch_attempt_id == attempt.pk
                    else "successful_source_observation"
                ),
                request_id=run.request_id,
                pipeline_run=run,
            )


def _failure_status(error: SafeFetchError) -> FetchStatus:
    if error.code in {
        "NETWORK_TARGET_BLOCKED",
        "URL_HOST_BLOCKED",
        "URL_SCHEME_BLOCKED",
        "URL_PORT_BLOCKED",
        "URL_USERINFO_BLOCKED",
    }:
        return FetchStatus.BLOCKED
    if error.code == "FETCH_RESPONSE_TOO_LARGE":
        return FetchStatus.TOO_LARGE
    if error.code in {"FETCH_CONTENT_TYPE_BLOCKED", "FETCH_EMPTY_BODY"}:
        return FetchStatus.UNSUPPORTED
    return FetchStatus.FAILED


def _record_failure(start: FetchStart, error: SafeFetchError) -> None:
    with transaction.atomic():
        attempt = FetchAttempt.objects.select_for_update().get(pk=start.attempt.pk)
        if attempt.status != FetchStatus.STARTED:
            return
        endpoint = SourceEndpoint.objects.select_for_update().get(pk=start.endpoint.pk)
        run = PipelineRun.objects.select_for_update().get(pk=start.pipeline_run.pk)
        candidate = SourceCandidate.objects.select_for_update().get(pk=start.candidate.pk)
        step = PipelineStepRun.objects.select_for_update().get(
            idempotency_key=f"sources.fetch:{run.pk}:effect"
        )
        now = timezone.now()
        attempt.status = _failure_status(error)
        attempt.network_policy = (
            NetworkPolicy.BLOCKED
            if attempt.status == FetchStatus.BLOCKED
            else NetworkPolicy.ALLOWED
        )
        attempt.final_url = redact_url(error.final_url) if error.final_url else ""
        attempt.http_status = error.status_code
        attempt.completed_at = now
        attempt.elapsed_ms = error.elapsed_ms
        attempt.redirect_chain = error.redirect_chain
        attempt.response_headers_filtered = error.headers_filtered
        attempt.retryable = error.retryable
        attempt.error_code = error.code
        attempt.safe_error_message = error.safe_message
        attempt.save(
            update_fields=(
                "status",
                "network_policy",
                "final_url",
                "http_status",
                "completed_at",
                "elapsed_ms",
                "redirect_chain",
                "response_headers_filtered",
                "retryable",
                "error_code",
                "safe_error_message",
            )
        )
        endpoint.last_failure_at = now
        endpoint.consecutive_failures += 1
        if endpoint.consecutive_failures >= 3:
            endpoint.status = EndpointStatus.DEGRADED
        endpoint.save(
            update_fields=(
                "last_failure_at",
                "consecutive_failures",
                "status",
                "updated_at",
            )
        )
        if error.retryable:
            candidate.status = CandidateStatus.FETCH_QUEUED
            run.status = PipelineStatus.QUEUED
            run.stage = "source_fetch_retry_wait"
            run.next_action_at = now
        else:
            candidate.status = (
                CandidateStatus.UNSAFE
                if attempt.status == FetchStatus.BLOCKED
                else CandidateStatus.REJECTED
            )
            candidate.rejection_reason = error.safe_message
            run.status = PipelineStatus.FAILED
            run.stage = "source_fetch_failed"
            run.completed_at = now
            run.error_count += 1
        candidate.save(update_fields=("status", "rejection_reason"))
        step.status = StepStatus.FAILED
        step.completed_at = now
        step.heartbeat_at = now
        step.last_error_code = error.code
        step.last_error_message = error.safe_message
        step.save(
            update_fields=(
                "status",
                "completed_at",
                "heartbeat_at",
                "last_error_code",
                "last_error_message",
                "updated_at",
            )
        )
        run.heartbeat_at = now
        run.last_error_code = error.code
        run.last_error_message = error.safe_message
        run.row_version += 1
        run.save(
            update_fields=(
                "status",
                "stage",
                "next_action_at",
                "completed_at",
                "error_count",
                "heartbeat_at",
                "last_error_code",
                "last_error_message",
                "row_version",
                "updated_at",
            )
        )
        AuditEvent.objects.create(
            actor_type=ActorType.SYSTEM,
            action=(
                "sources.public_source_blocked"
                if attempt.status == FetchStatus.BLOCKED
                else "sources.public_source_fetch_failed"
            ),
            object_type="source_endpoint",
            object_id=endpoint.pk,
            after_summary={
                "status": attempt.status,
                "error_code": error.code,
                "retryable": error.retryable,
                "fetch_attempt_id": str(attempt.pk),
            },
            reason_key="safe_fetch_policy"
            if attempt.status == FetchStatus.BLOCKED
            else "fetch_error",
            request_id=run.request_id,
            pipeline_run=run,
        )


def execute_source_fetch(
    envelope: TaskEnvelopeV2,
    *,
    policy: FetchPolicySettings,
    fetcher: Fetcher | None = None,
    recover_started: bool = False,
) -> FetchAttempt:
    start = _begin_fetch(envelope, recover_started=recover_started)
    if not start.should_fetch:
        return start.attempt
    active_fetcher = fetcher or SafeHttpFetcher(policy)
    try:
        result = active_fetcher.fetch(
            start.endpoint.base_url_canonical,
            etag=start.endpoint.etag,
            last_modified=start.endpoint.last_modified,
        )
        storage_key = ""
        if result.status_code != 304:
            storage_key = _persist_body(start.endpoint, result)
        _complete_fetch(start, result, storage_key)
    except SafeFetchError as exc:
        _record_failure(start, exc)
        if exc.retryable:
            raise RetryableFetchError(exc.safe_message) from exc
    except OSError as exc:
        storage_error = SafeFetchError(
            "ARTIFACT_STORAGE_FAILED",
            "The immutable source artifact could not be stored.",
            retryable=True,
        )
        _record_failure(start, storage_error)
        raise RetryableFetchError(storage_error.safe_message) from exc
    return FetchAttempt.objects.get(pk=start.attempt.pk)


def mark_fetch_exhausted(*, pipeline_run_id: UUID) -> None:
    with transaction.atomic():
        run = PipelineRun.objects.select_for_update().get(pk=pipeline_run_id)
        if run.status == PipelineStatus.COMPLETE:
            return
        candidate = SourceCandidate.objects.select_for_update().get(pipeline_run=run)
        if run.object_id is None:
            raise ValueError("The source fetch run does not identify a source endpoint.")
        endpoint = SourceEndpoint.objects.select_for_update().get(pk=run.object_id)
        now = timezone.now()
        run.status = PipelineStatus.FAILED
        run.stage = "source_fetch_exhausted"
        run.completed_at = now
        run.next_action_at = None
        run.error_count += 1
        run.last_error_code = "FETCH_RETRIES_EXHAUSTED"
        run.last_error_message = "The source could not be fetched after bounded retries."
        run.row_version += 1
        run.save(
            update_fields=(
                "status",
                "stage",
                "completed_at",
                "next_action_at",
                "error_count",
                "last_error_code",
                "last_error_message",
                "row_version",
                "updated_at",
            )
        )
        candidate.status = CandidateStatus.REJECTED
        candidate.rejection_reason = run.last_error_message
        candidate.save(update_fields=("status", "rejection_reason"))
        endpoint.status = EndpointStatus.DEGRADED
        endpoint.save(update_fields=("status", "updated_at"))
        AuditEvent.objects.create(
            actor_type=ActorType.SYSTEM,
            action="sources.public_source_fetch_exhausted",
            object_type="source_endpoint",
            object_id=endpoint.pk,
            after_summary={"status": EndpointStatus.DEGRADED},
            reason_key="bounded_retry_exhausted",
            request_id=run.request_id,
            pipeline_run=run,
        )
