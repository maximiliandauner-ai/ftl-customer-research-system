from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import cast
from uuid import UUID

from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.companies.models import Company, CompanyStatus, DomainVerificationStatus
from apps.jobs.connectors import ConnectorError, parse_source
from apps.jobs.connectors.text import normalize_text
from apps.jobs.contracts import ConnectorParseResultV1, ParsedPostingV1
from apps.jobs.models import (
    ClosureReason,
    ConnectorParseAttempt,
    DuplicateMethod,
    DuplicateRelationship,
    DuplicateRelationshipType,
    DuplicateReviewStatus,
    JobLocation,
    JobPosting,
    JobPostingSnapshot,
    ObservationState,
    ParseStatus,
    PostingChangeEvent,
    PostingChangeType,
    PostingLifecycle,
    PostingObservation,
)
from apps.operations.commands import JOBS_PARSE_COMMAND_TYPE
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
from apps.sources.models import EndpointStatus, FetchAttempt, ProviderType, SourceSnapshot
from apps.sources.policy import normalize_company_name

NORMALIZER_VERSION = "1.1.0"
CHANGE_POLICY_VERSION = "1.0.0"
CLOSURE_ABSENCE_THRESHOLD = 2
MAX_ARTIFACT_BYTES = 10_485_760


class RetryableParseError(RuntimeError):
    pass


class ArtifactIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class ParseStart:
    attempt: ConnectorParseAttempt
    snapshot: SourceSnapshot
    pipeline_run: PipelineRun
    should_parse: bool


def schedule_parse_for_snapshot(
    source_snapshot: SourceSnapshot,
    *,
    source_run: PipelineRun,
    fetch_attempt: FetchAttempt,
) -> tuple[PipelineRun, TaskOutbox, bool]:
    run_key = f"jobs.normalize:{source_snapshot.pk}:{fetch_attempt.pk}:{NORMALIZER_VERSION}"
    run, created = PipelineRun.objects.get_or_create(
        idempotency_key=run_key,
        defaults={
            "pipeline_name": "jobs.normalization",
            "stage": "parse_queued",
            "status": PipelineStatus.QUEUED,
            "trigger": source_run.trigger,
            "requested_by": source_run.requested_by,
            "request_id": source_run.request_id,
            "object_type": "source_snapshot",
            "object_id": source_snapshot.pk,
            "heartbeat_at": timezone.now(),
            "input_count": 1,
            "policy_versions": {
                "connector_registry": "1.0.0",
                "normalizer": NORMALIZER_VERSION,
            },
            "context": {
                "source_endpoint_id": str(source_snapshot.source_endpoint_id),
                "source_pipeline_run_id": str(source_run.pk),
                "fetch_attempt_id": str(fetch_attempt.pk),
                "reprocess": False,
            },
        },
    )
    payload = TargetCommandPayloadV1(pipeline_run_id=run.pk, object_id=source_snapshot.pk)
    outbox, outbox_created = TaskOutbox.objects.get_or_create(
        idempotency_key=f"jobs.parse:{source_snapshot.pk}:{fetch_attempt.pk}:{NORMALIZER_VERSION}",
        defaults={
            "command_type": JOBS_PARSE_COMMAND_TYPE,
            "payload": payload.model_dump(mode="json"),
            "payload_schema_version": "1.0",
            "pipeline_run": run,
            "request_id": source_run.request_id,
        },
    )
    if outbox_created:
        outbox.full_clean()
    return run, outbox, created and outbox_created


def create_reparse_command(source_snapshot: SourceSnapshot) -> tuple[PipelineRun, TaskOutbox, bool]:
    with transaction.atomic():
        now_key = timezone.now().strftime("%Y%m%dT%H%M%S%f")
        run = PipelineRun.objects.create(
            pipeline_name="jobs.normalization",
            stage="parse_queued",
            status=PipelineStatus.QUEUED,
            trigger=PipelineTrigger.BACKFILL,
            idempotency_key=f"jobs.reparse:{source_snapshot.pk}:{NORMALIZER_VERSION}:{now_key}",
            object_type="source_snapshot",
            object_id=source_snapshot.pk,
            heartbeat_at=timezone.now(),
            input_count=1,
            policy_versions={"connector_registry": "1.0.0", "normalizer": NORMALIZER_VERSION},
            context={
                "source_endpoint_id": str(source_snapshot.source_endpoint_id),
                "fetch_attempt_id": str(source_snapshot.fetch_attempt_id),
                "reprocess": True,
            },
        )
        payload = TargetCommandPayloadV1(pipeline_run_id=run.pk, object_id=source_snapshot.pk)
        outbox = TaskOutbox(
            command_type=JOBS_PARSE_COMMAND_TYPE,
            payload=payload.model_dump(mode="json"),
            payload_schema_version="1.0",
            idempotency_key=f"jobs.reparse-command:{run.pk}",
            pipeline_run=run,
        )
        outbox.full_clean()
        outbox.save()
        return run, outbox, True


def _begin_parse(envelope: TaskEnvelopeV2, *, recover_started: bool) -> ParseStart:
    if envelope.command_type != JOBS_PARSE_COMMAND_TYPE:
        raise ValueError("Unsupported job-parse command type.")
    with transaction.atomic():
        run = PipelineRun.objects.select_for_update().get(pk=envelope.pipeline_run_id)
        snapshot = SourceSnapshot.objects.select_related("artifact", "source_endpoint").get(
            pk=envelope.object_id
        )
        outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=run)
        if outbox.idempotency_key != envelope.idempotency_key:
            raise ValueError("Envelope idempotency does not match the job parse command.")
        existing = ConnectorParseAttempt.objects.filter(pipeline_run=run).first()
        if existing is not None and existing.status != ParseStatus.STARTED:
            return ParseStart(existing, snapshot, run, False)
        if existing is not None and not recover_started:
            return ParseStart(existing, snapshot, run, False)
        if existing is not None:
            now = timezone.now()
            existing.started_at = now
            existing.completed_at = None
            existing.error_code = ""
            existing.safe_error_message = ""
            existing.save(
                update_fields=(
                    "started_at",
                    "completed_at",
                    "error_code",
                    "safe_error_message",
                )
            )
            recovery_key = f"jobs.parse:{run.pk}:recovery:{run.attempts + 1}"
            PipelineStepRun.objects.create(
                pipeline_run=run,
                stage="connector_parse",
                status=StepStatus.RUNNING,
                idempotency_key=recovery_key,
                attempt=run.attempts + 1,
                started_at=now,
                heartbeat_at=now,
                input_ids={
                    "source_snapshot_id": str(snapshot.pk),
                    "source_artifact_id": str(snapshot.artifact_id),
                },
            )
            run.status = PipelineStatus.RUNNING
            run.stage = "connector_parse"
            run.heartbeat_at = now
            run.attempts += 1
            run.row_version += 1
            run.save(
                update_fields=(
                    "status",
                    "stage",
                    "heartbeat_at",
                    "attempts",
                    "row_version",
                    "updated_at",
                )
            )
            return ParseStart(existing, snapshot, run, True)
        else:
            recovery_key = f"jobs.parse:{run.pk}:effect"
        now = timezone.now()
        attempt = ConnectorParseAttempt.objects.create(
            source_snapshot=snapshot,
            pipeline_run=run,
            status=ParseStatus.STARTED,
            normalizer_version=NORMALIZER_VERSION,
            detected_content_type=snapshot.content_type,
            started_at=now,
        )
        PipelineStepRun.objects.create(
            pipeline_run=run,
            stage="connector_parse",
            status=StepStatus.RUNNING,
            idempotency_key=recovery_key,
            attempt=run.attempts + 1,
            started_at=now,
            heartbeat_at=now,
            input_ids={
                "source_snapshot_id": str(snapshot.pk),
                "source_artifact_id": str(snapshot.artifact_id),
            },
        )
        run.status = PipelineStatus.RUNNING
        run.stage = "connector_parse"
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
        return ParseStart(attempt, snapshot, run, True)


def _read_verified_artifact(snapshot: SourceSnapshot) -> bytes:
    artifact = snapshot.artifact
    if artifact.size_bytes > MAX_ARTIFACT_BYTES:
        raise ArtifactIntegrityError("The stored source artifact exceeds the parse size policy.")
    try:
        with default_storage.open(artifact.storage_key, "rb") as handle:
            body = cast(bytes, handle.read(MAX_ARTIFACT_BYTES + 1))
    except OSError as exc:
        raise RetryableParseError("The source artifact is temporarily unavailable.") from exc
    if len(body) != artifact.size_bytes or len(body) > MAX_ARTIFACT_BYTES:
        raise ArtifactIntegrityError("The stored source artifact size does not match its metadata.")
    if hashlib.sha256(body).hexdigest() != artifact.sha256:
        raise ArtifactIntegrityError("The stored source artifact hash does not match its metadata.")
    if snapshot.body_sha256 != artifact.sha256:
        raise ArtifactIntegrityError("The source snapshot and artifact hashes do not match.")
    return body


def _company_for(endpoint_company: Company | None, posting: ParsedPostingV1) -> Company:
    if endpoint_company is not None:
        return endpoint_company
    if not posting.company_name:
        raise ConnectorError(
            "COMPANY_UNRESOLVED",
            "The source has no mapped company and the posting has no source-backed employer.",
        )
    normalized = normalize_company_name(posting.company_name)
    matching = Company.objects.filter(normalized_name=normalized).order_by("pk").first()
    return matching or Company.objects.create(
        name=posting.company_name,
        normalized_name=normalized,
        status=CompanyStatus.PROVISIONAL,
    )


def _provider_type(connector_key: str) -> str:
    return {
        "personio": ProviderType.PERSONIO,
        "greenhouse": ProviderType.GREENHOUSE,
        "lever": ProviderType.LEVER,
        "ashby": ProviderType.ASHBY,
        "json_ld": ProviderType.JSON_LD,
        "generic_html": ProviderType.GENERIC_WEB,
    }[connector_key]


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _posting_hashes(
    posting: ParsedPostingV1, connector_key: str, connector_version: str
) -> tuple[str, str]:
    full = posting.model_dump(mode="json")
    full["connector_key"] = connector_key
    full["connector_version"] = connector_version
    full["normalizer_version"] = NORMALIZER_VERSION
    semantic = {
        "title": posting.title.casefold(),
        "description_text": posting.description_text.casefold(),
        "department": posting.department.casefold(),
        "team": posting.team.casefold(),
        "employment_type": posting.employment_type.casefold(),
        "locations": [
            {
                "display": location.display_text.casefold(),
                "remote": location.remote,
                "workplace": location.workplace_type,
            }
            for location in posting.locations
        ],
    }
    return _canonical_hash(full), _canonical_hash(semantic)


def _changed_fields(
    old: JobPostingSnapshot | None,
    new: JobPostingSnapshot,
) -> list[str]:
    if old is None:
        return ["posting"]
    changed: list[str] = []
    comparisons = {
        "title": (old.title, new.title),
        "description_text": (old.description_text, new.description_text),
        "locations": (old.locations_payload, new.locations_payload),
        "normalizer_version": (old.normalizer_version, new.normalizer_version),
    }
    for key in (
        "department",
        "team",
        "employment_type",
        "language",
        "published_at",
        "valid_through",
        "canonical_url",
        "apply_url",
    ):
        comparisons[f"metadata.{key}"] = (old.metadata.get(key), new.metadata.get(key))
    for field_path, (before, after) in comparisons.items():
        if before != after:
            changed.append(field_path)
    return sorted(changed)


def _change_type(
    *,
    created: bool,
    was_closed: bool,
    parsed_is_open: bool,
    old: JobPostingSnapshot | None,
    new: JobPostingSnapshot,
) -> str:
    if not parsed_is_open:
        return PostingChangeType.CLOSED if not was_closed else PostingChangeType.UNCHANGED
    if was_closed:
        return PostingChangeType.REOPENED
    if created or old is None:
        return PostingChangeType.CREATED
    if old.full_hash == new.full_hash:
        return PostingChangeType.UNCHANGED
    if old.semantic_hash == new.semantic_hash:
        return PostingChangeType.COSMETIC
    return PostingChangeType.MATERIAL


def _record_change(
    *,
    posting: JobPosting,
    source_snapshot: SourceSnapshot,
    observation: PostingObservation,
    run: PipelineRun,
    old_snapshot: JobPostingSnapshot | None,
    new_snapshot: JobPostingSnapshot | None,
    change_type: str,
    changed_fields: list[str],
) -> PostingChangeEvent:
    event = PostingChangeEvent.objects.create(
        posting=posting,
        source_snapshot=source_snapshot,
        observation=observation,
        parse_run=run,
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        change_type=change_type,
        changed_fields=changed_fields,
        before_full_hash=old_snapshot.full_hash if old_snapshot else "",
        after_full_hash=new_snapshot.full_hash if new_snapshot else "",
        policy_version=CHANGE_POLICY_VERSION,
        idempotency_key=f"jobs.change:{observation.pk}:{CHANGE_POLICY_VERSION}",
        occurred_at=observation.observed_at,
    )
    if change_type in {
        PostingChangeType.CREATED,
        PostingChangeType.MATERIAL,
        PostingChangeType.CLOSED,
        PostingChangeType.REOPENED,
    }:
        from apps.signals.services import schedule_signal_detection

        schedule_signal_detection(event)
    return event


def _audit_lifecycle(
    *,
    posting: JobPosting,
    run: PipelineRun,
    before: str,
    after: str,
    reason_key: str,
) -> None:
    AuditEvent.objects.create(
        actor_type=ActorType.SYSTEM,
        action=f"jobs.posting_{after}",
        object_type="job_posting",
        object_id=posting.pk,
        before_summary={"lifecycle_status": before, "row_version": posting.row_version - 1},
        after_summary={"lifecycle_status": after, "row_version": posting.row_version},
        reason_key=reason_key,
        request_id=run.request_id,
        pipeline_run=run,
    )


def _link_exact_duplicates(posting: JobPosting) -> None:
    current = posting.current_snapshot
    if current is None:
        return
    verified_company = posting.company.domains.filter(
        verification_status__in=(
            DomainVerificationStatus.SOURCE_CONFIRMED,
            DomainVerificationStatus.HUMAN_VERIFIED,
        )
    ).exists()
    candidates = (
        JobPosting.objects.select_related("current_snapshot")
        .filter(company=posting.company)
        .exclude(pk=posting.pk)
        .filter(
            Q(canonical_url=posting.canonical_url)
            | Q(current_snapshot__semantic_hash=current.semantic_hash)
        )
    )
    for other in candidates:
        same_url = other.canonical_url == posting.canonical_url
        if not same_url and not verified_company:
            continue
        primary, secondary = sorted((posting, other), key=lambda item: str(item.pk))
        method = DuplicateMethod.CANONICAL_URL if same_url else DuplicateMethod.CONTENT_HASH
        DuplicateRelationship.objects.get_or_create(
            primary_posting=primary,
            secondary_posting=secondary,
            defaults={
                "relationship_type": DuplicateRelationshipType.DUPLICATE,
                "method": method,
                "confidence": "1.000" if same_url else "0.980",
                "review_status": DuplicateReviewStatus.AUTOMATIC,
                "source_priority": "first_party",
                "evidence": {
                    "canonical_url": posting.canonical_url if same_url else "",
                    "semantic_hash": current.semantic_hash if not same_url else "",
                },
            },
        )


def _persist_result(start: ParseStart, result: ConnectorParseResultV1, elapsed_ms: int) -> None:
    provider_type = _provider_type(result.connector_key)
    with transaction.atomic():
        attempt = ConnectorParseAttempt.objects.select_for_update().get(pk=start.attempt.pk)
        if attempt.status != ParseStatus.STARTED:
            return
        run = PipelineRun.objects.select_for_update().get(pk=start.pipeline_run.pk)
        snapshot = SourceSnapshot.objects.select_related("source_endpoint__company").get(
            pk=start.snapshot.pk
        )
        endpoint = snapshot.source_endpoint
        now = timezone.now()
        fetch_attempt_id = UUID(str(run.context.get("fetch_attempt_id", snapshot.fetch_attempt_id)))
        fetch_attempt = FetchAttempt.objects.get(pk=fetch_attempt_id, source_endpoint=endpoint)
        observed_at = fetch_attempt.completed_at or snapshot.retrieved_at
        reprocess = bool(run.context.get("reprocess", False))
        posting_ids: list[str] = []
        present_posting_ids: set[UUID] = set()
        new_snapshot_count = 0
        for parsed in result.postings:
            company = _company_for(endpoint.company, parsed)
            posting, created = JobPosting.objects.select_for_update().get_or_create(
                primary_source_endpoint=endpoint,
                provider_type=provider_type,
                external_posting_id=parsed.external_id,
                defaults={
                    "company": company,
                    "canonical_url": parsed.canonical_url,
                    "apply_url": parsed.apply_url,
                    "source_url": endpoint.base_url_canonical,
                    "title": parsed.title,
                    "normalized_title": normalize_text(parsed.title).casefold(),
                    "department": parsed.department,
                    "team": parsed.team,
                    "employment_type": parsed.employment_type,
                    "language": parsed.language,
                    "lifecycle_status": PostingLifecycle.OPEN,
                    "first_seen_at": snapshot.retrieved_at,
                    "last_seen_at": snapshot.retrieved_at,
                },
            )
            if not created and posting.company_id != company.pk:
                raise ConnectorError(
                    "POSTING_COMPANY_CONFLICT",
                    "The provider identity is already bound to a different company.",
                )
            old_snapshot = posting.current_snapshot
            was_closed = posting.lifecycle_status == PostingLifecycle.CLOSED
            full_hash, semantic_hash = _posting_hashes(
                parsed, result.connector_key, result.connector_version
            )
            normalized_snapshot = JobPostingSnapshot.objects.filter(
                posting=posting,
                full_hash=full_hash,
            ).first()
            if normalized_snapshot is None:
                normalized_snapshot = JobPostingSnapshot.objects.create(
                    posting=posting,
                    source_snapshot=snapshot,
                    parse_run=run,
                    connector_key=result.connector_key,
                    connector_version=result.connector_version,
                    normalizer_version=NORMALIZER_VERSION,
                    retrieved_at=snapshot.retrieved_at,
                    title=parsed.title,
                    description_text=parsed.description_text,
                    structured_sections=[
                        section.model_dump(mode="json") for section in parsed.sections
                    ],
                    metadata={
                        "department": parsed.department,
                        "team": parsed.team,
                        "employment_type": parsed.employment_type,
                        "language": parsed.language,
                        "published_at": parsed.published_at,
                        "valid_through": parsed.valid_through,
                        "canonical_url": parsed.canonical_url,
                        "apply_url": parsed.apply_url,
                        "company_name": parsed.company_name,
                        "company_url": parsed.company_url,
                    },
                    locations_payload=[
                        location.model_dump(mode="json") for location in parsed.locations
                    ],
                    full_hash=full_hash,
                    semantic_hash=semantic_hash,
                )
                new_snapshot_count += 1
            observation, observation_created = PostingObservation.objects.get_or_create(
                posting=posting,
                fetch_attempt=fetch_attempt,
                defaults={
                    "source_snapshot": snapshot,
                    "parse_run": run,
                    "state": (
                        ObservationState.FOUND
                        if parsed.is_open
                        else ObservationState.EXPLICIT_CLOSED
                    ),
                    "provider_identity": parsed.external_id,
                    "observed_url": parsed.canonical_url,
                    "observed_at": observed_at,
                },
            )
            JobLocation.objects.filter(posting=posting).delete()
            JobLocation.objects.bulk_create(
                [
                    JobLocation(
                        posting=posting,
                        ordinal=index,
                        display_text=location.display_text,
                        city=location.city,
                        region=location.region,
                        country=location.country,
                        postal_code=location.postal_code,
                        remote=location.remote,
                        workplace_type=location.workplace_type,
                    )
                    for index, location in enumerate(parsed.locations)
                ]
            )
            posting.current_snapshot = normalized_snapshot
            posting.canonical_url = parsed.canonical_url
            posting.apply_url = parsed.apply_url
            posting.title = parsed.title
            posting.normalized_title = normalize_text(parsed.title).casefold()
            posting.department = parsed.department
            posting.team = parsed.team
            posting.employment_type = parsed.employment_type
            posting.language = parsed.language
            posting.lifecycle_status = (
                PostingLifecycle.OPEN if parsed.is_open else PostingLifecycle.CLOSED
            )
            posting.successful_absence_count = 0
            posting.closed_at = None if parsed.is_open else posting.closed_at or now
            posting.closure_reason = "" if parsed.is_open else ClosureReason.EXPLICIT_PROVIDER
            posting.last_seen_at = max(posting.last_seen_at, observed_at)
            posting.row_version += 1
            posting.save(
                update_fields=(
                    "current_snapshot",
                    "canonical_url",
                    "apply_url",
                    "title",
                    "normalized_title",
                    "department",
                    "team",
                    "employment_type",
                    "language",
                    "lifecycle_status",
                    "successful_absence_count",
                    "closed_at",
                    "closure_reason",
                    "last_seen_at",
                    "row_version",
                    "updated_at",
                )
            )
            if observation_created and not reprocess:
                change_type = _change_type(
                    created=created,
                    was_closed=was_closed,
                    parsed_is_open=parsed.is_open,
                    old=old_snapshot,
                    new=normalized_snapshot,
                )
                changed = _changed_fields(old_snapshot, normalized_snapshot)
                if change_type == PostingChangeType.REOPENED:
                    changed.append("lifecycle_status")
                elif change_type == PostingChangeType.CLOSED:
                    changed.extend(("lifecycle_status", "closure_reason"))
                _record_change(
                    posting=posting,
                    source_snapshot=snapshot,
                    observation=observation,
                    run=run,
                    old_snapshot=old_snapshot,
                    new_snapshot=normalized_snapshot,
                    change_type=change_type,
                    changed_fields=sorted(set(changed)),
                )
                if change_type == PostingChangeType.REOPENED:
                    _audit_lifecycle(
                        posting=posting,
                        run=run,
                        before=PostingLifecycle.CLOSED,
                        after=PostingLifecycle.OPEN,
                        reason_key="successful_reappearance",
                    )
                elif change_type == PostingChangeType.CLOSED:
                    _audit_lifecycle(
                        posting=posting,
                        run=run,
                        before=PostingLifecycle.OPEN,
                        after=PostingLifecycle.CLOSED,
                        reason_key=ClosureReason.EXPLICIT_PROVIDER,
                    )
            posting_ids.append(str(posting.pk))
            present_posting_ids.add(posting.pk)
            _link_exact_duplicates(posting)
        if result.collection_complete and not reprocess:
            missing_postings = (
                JobPosting.objects.select_for_update()
                .filter(primary_source_endpoint=endpoint, provider_type=provider_type)
                .exclude(pk__in=present_posting_ids)
            )
            for missing in missing_postings:
                observation, observation_created = PostingObservation.objects.get_or_create(
                    posting=missing,
                    fetch_attempt=fetch_attempt,
                    defaults={
                        "source_snapshot": snapshot,
                        "parse_run": run,
                        "state": ObservationState.MISSING,
                        "provider_identity": missing.external_posting_id,
                        "observed_url": missing.canonical_url,
                        "observed_at": fetch_attempt.completed_at or now,
                    },
                )
                if not observation_created:
                    continue
                missing.successful_absence_count = min(
                    missing.successful_absence_count + 1,
                    CLOSURE_ABSENCE_THRESHOLD,
                )
                if (
                    missing.successful_absence_count >= CLOSURE_ABSENCE_THRESHOLD
                    and missing.lifecycle_status != PostingLifecycle.CLOSED
                ):
                    before = missing.lifecycle_status
                    missing.lifecycle_status = PostingLifecycle.CLOSED
                    missing.closed_at = fetch_attempt.completed_at or now
                    missing.closure_reason = ClosureReason.CONSECUTIVE_ABSENCE
                    missing.row_version += 1
                    missing.save(
                        update_fields=(
                            "successful_absence_count",
                            "lifecycle_status",
                            "closed_at",
                            "closure_reason",
                            "row_version",
                            "updated_at",
                        )
                    )
                    _record_change(
                        posting=missing,
                        source_snapshot=snapshot,
                        observation=observation,
                        run=run,
                        old_snapshot=missing.current_snapshot,
                        new_snapshot=missing.current_snapshot,
                        change_type=PostingChangeType.CLOSED,
                        changed_fields=[
                            "lifecycle_status",
                            "successful_absence_count",
                            "closure_reason",
                        ],
                    )
                    _audit_lifecycle(
                        posting=missing,
                        run=run,
                        before=before,
                        after=PostingLifecycle.CLOSED,
                        reason_key=ClosureReason.CONSECUTIVE_ABSENCE,
                    )
                else:
                    missing.row_version += 1
                    missing.save(
                        update_fields=(
                            "successful_absence_count",
                            "row_version",
                            "updated_at",
                        )
                    )
        endpoint.provider_type = provider_type
        endpoint.connector_key = result.connector_key
        endpoint.connector_version = result.connector_version
        endpoint.status = EndpointStatus.ACTIVE
        endpoint.last_schema_change_at = None
        endpoint.save(
            update_fields=(
                "provider_type",
                "connector_key",
                "connector_version",
                "status",
                "last_schema_change_at",
                "updated_at",
            )
        )
        if provider_type in {
            ProviderType.PERSONIO,
            ProviderType.GREENHOUSE,
            ProviderType.LEVER,
            ProviderType.ASHBY,
        }:
            from apps.discovery.models import EndpointWatch

            EndpointWatch.objects.get_or_create(
                source_endpoint=endpoint,
                defaults={"next_poll_at": now + timedelta(hours=24)},
            )
        attempt.status = ParseStatus.SUCCEEDED
        attempt.connector_key = result.connector_key
        attempt.connector_version = result.connector_version
        attempt.posting_count = len(result.postings)
        attempt.snapshot_count = new_snapshot_count
        attempt.warning_count = len(result.warnings)
        attempt.warnings = list(result.warnings)
        attempt.completed_at = now
        attempt.elapsed_ms = elapsed_ms
        attempt.save(
            update_fields=(
                "status",
                "connector_key",
                "connector_version",
                "posting_count",
                "snapshot_count",
                "warning_count",
                "warnings",
                "completed_at",
                "elapsed_ms",
            )
        )
        step = (
            PipelineStepRun.objects.select_for_update()
            .filter(pipeline_run=run, status=StepStatus.RUNNING)
            .order_by("-created_at")
            .first()
        )
        if step is not None:
            step.status = StepStatus.COMPLETE
            step.completed_at = now
            step.heartbeat_at = now
            step.output_ids = {"posting_ids": posting_ids, "parse_attempt_id": str(attempt.pk)}
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
        run.stage = "normalization_complete"
        run.completed_at = now
        run.heartbeat_at = now
        run.output_count = len(posting_ids)
        run.warning_count = len(result.warnings)
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
                "warning_count",
                "last_error_code",
                "last_error_message",
                "row_version",
                "updated_at",
            )
        )
        AuditEvent.objects.create(
            actor_type=ActorType.SYSTEM,
            action="jobs.source_snapshot_normalized",
            object_type="source_snapshot",
            object_id=snapshot.pk,
            after_summary={
                "connector_key": result.connector_key,
                "connector_version": result.connector_version,
                "normalizer_version": NORMALIZER_VERSION,
                "posting_count": len(posting_ids),
                "new_snapshot_count": new_snapshot_count,
                "posting_ids": posting_ids,
            },
            reason_key="deterministic_connector",
            request_id=run.request_id,
            pipeline_run=run,
        )


def _fail_parse(
    start: ParseStart,
    *,
    status: str,
    error_code: str,
    safe_message: str,
    elapsed_ms: int,
) -> None:
    with transaction.atomic():
        attempt = ConnectorParseAttempt.objects.select_for_update().get(pk=start.attempt.pk)
        if attempt.status != ParseStatus.STARTED:
            return
        run = PipelineRun.objects.select_for_update().get(pk=start.pipeline_run.pk)
        endpoint = start.snapshot.source_endpoint
        now = timezone.now()
        attempt.status = status
        attempt.completed_at = now
        attempt.elapsed_ms = elapsed_ms
        attempt.error_code = error_code
        attempt.safe_error_message = safe_message[:500]
        attempt.save(
            update_fields=(
                "status",
                "completed_at",
                "elapsed_ms",
                "error_code",
                "safe_error_message",
            )
        )
        PipelineStepRun.objects.filter(pipeline_run=run, status=StepStatus.RUNNING).update(
            status=StepStatus.FAILED,
            completed_at=now,
            heartbeat_at=now,
            last_error_code=error_code,
            last_error_message=safe_message[:500],
        )
        run.status = PipelineStatus.FAILED
        run.stage = "normalization_failed"
        run.completed_at = now
        run.heartbeat_at = now
        run.error_count = 1
        run.last_error_code = error_code
        run.last_error_message = safe_message[:500]
        run.row_version += 1
        run.save(
            update_fields=(
                "status",
                "stage",
                "completed_at",
                "heartbeat_at",
                "error_count",
                "last_error_code",
                "last_error_message",
                "row_version",
                "updated_at",
            )
        )
        endpoint.status = EndpointStatus.DEGRADED
        endpoint.last_schema_change_at = now
        endpoint.save(update_fields=("status", "last_schema_change_at", "updated_at"))
        AuditEvent.objects.create(
            actor_type=ActorType.SYSTEM,
            action="jobs.source_snapshot_normalization_failed",
            object_type="source_snapshot",
            object_id=start.snapshot.pk,
            after_summary={"status": status, "error_code": error_code},
            reason_key="connector_failure",
            request_id=run.request_id,
            pipeline_run=run,
        )


def execute_source_parse(envelope: TaskEnvelopeV2, *, recover_started: bool = False) -> None:
    start = _begin_parse(envelope, recover_started=recover_started)
    if not start.should_parse:
        return
    started = time.monotonic()
    try:
        body = _read_verified_artifact(start.snapshot)
        result = parse_source(
            start.snapshot.source_endpoint,
            body,
            content_type=start.snapshot.content_type,
            encoding=start.snapshot.encoding or "utf-8",
        )
        elapsed_ms = max(0, int((time.monotonic() - started) * 1_000))
        _persist_result(start, result, elapsed_ms)
    except ConnectorError as exc:
        elapsed_ms = max(0, int((time.monotonic() - started) * 1_000))
        status = (
            ParseStatus.UNSUPPORTED
            if "UNSUPPORTED" in exc.code or "NO_JOBS" in exc.code
            else ParseStatus.INVALID_SCHEMA
        )
        _fail_parse(
            start,
            status=status,
            error_code=exc.code,
            safe_message=exc.safe_message,
            elapsed_ms=elapsed_ms,
        )
    except ArtifactIntegrityError as exc:
        elapsed_ms = max(0, int((time.monotonic() - started) * 1_000))
        _fail_parse(
            start,
            status=ParseStatus.FAILED,
            error_code="ARTIFACT_INTEGRITY_FAILED",
            safe_message=str(exc),
            elapsed_ms=elapsed_ms,
        )
    except IntegrityError:
        elapsed_ms = max(0, int((time.monotonic() - started) * 1_000))
        _fail_parse(
            start,
            status=ParseStatus.FAILED,
            error_code="NORMALIZATION_CONSTRAINT_FAILED",
            safe_message="The normalized records conflicted with a database constraint.",
            elapsed_ms=elapsed_ms,
        )


def mark_parse_exhausted(*, pipeline_run_id: UUID) -> None:
    start_attempt = ConnectorParseAttempt.objects.filter(pipeline_run_id=pipeline_run_id).first()
    if start_attempt is None or start_attempt.status != ParseStatus.STARTED:
        return
    snapshot = SourceSnapshot.objects.select_related("source_endpoint", "artifact").get(
        pk=start_attempt.source_snapshot_id
    )
    run = PipelineRun.objects.get(pk=pipeline_run_id)
    _fail_parse(
        ParseStart(start_attempt, snapshot, run, True),
        status=ParseStatus.FAILED,
        error_code="PARSE_RETRIES_EXHAUSTED",
        safe_message="The parser could not read its durable source artifact after retries.",
        elapsed_ms=0,
    )
