from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.jobs.models import (
    EvidenceCatalog,
    EvidenceItem,
    JobPostingSnapshot,
    PostingChangeEvent,
    PostingChangeType,
)
from apps.operations.commands import SIGNALS_DETECT_COMMAND_TYPE
from apps.operations.contracts import TargetCommandPayloadV1, TaskEnvelopeV2
from apps.operations.models import (
    ActorType,
    AuditEvent,
    PipelineRun,
    PipelineStatus,
    PipelineStepRun,
    StepStatus,
    TaskOutbox,
)
from apps.signals.contracts import SignalCandidateV2, SignalDetectionResultV2
from apps.signals.models import (
    AssessmentStatus,
    DetectionMethod,
    DetectionStatus,
    SignalDetectionAttempt,
    SignalEvent,
    SignalEvidence,
    SignalOntology,
    SignalReviewState,
    SignalStatus,
    SignalType,
)

EVIDENCE_BUILDER_VERSION = "1.0.0"
DETECTOR_VERSION = "1.0.2"
ONTOLOGY_VERSION = "1.0.2"
PROMPT_VERSION = "2.0.0"
SCHEMA_VERSION = "2.0"
MAX_EVIDENCE_TEXT = 800
ELIGIBLE_CHANGE_TYPES = {
    PostingChangeType.CREATED,
    PostingChangeType.MATERIAL,
    PostingChangeType.CLOSED,
    PostingChangeType.REOPENED,
}

CAPABILITY_RULES: dict[str, tuple[str, ...]] = {
    "creative_ai_production": (
        "ai-generated video",
        "ai generated video",
        "generative video",
        "runway",
        "comfyui",
        "synthetic media",
    ),
    "learning_content": (
        "learning content",
        "lerncontent",
        "e-learning",
        "elearning",
        "digital learning",
        "instructional design",
        "training materials",
        "academy content",
    ),
    "workflow_automation": (
        "workflow automation",
        "process automation",
        "automatisierung",
        "automate workflows",
        "internal tools",
        "prompt templates",
    ),
    "knowledge_systems": (
        "knowledge management",
        "knowledge base",
        "wissensmanagement",
        "retrieval augmented",
        "rag system",
    ),
    "ai_enablement": (
        "ai enablement",
        "train employees on ai",
        "ai employee training",
        "ai workshops",
        "ki-workshops",
        "ki workshops",
        "ki-schulungen",
        "ki schulungen",
        "ai adoption",
        "ai change management",
        "change management for ai",
    ),
    "data_integration": (
        "data integration",
        "api integration",
        "system integration",
        "etl",
        "crm integration",
    ),
    "local_private_ai": (
        "local llm",
        "on-premise ai",
        "on premises ai",
        "on-premise llm",
        "on premises llm",
        "private ai",
        "private llm",
    ),
}

SUSPICIOUS_PATTERNS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "assistant message",
    "return json",
    "create a signal",
    "reveal secret",
    "credentials",
)

COMMERCIAL_TERMS = (
    "ftl",
    "buyer",
    "budget",
    "outreach",
    "vendor",
    "purchase",
    "sales opportunity",
    "recommend our",
)


class SignalValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ScheduledDetection:
    run: PipelineRun
    attempt: SignalDetectionAttempt
    outbox: TaskOutbox
    created: bool


def _canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _ontology_payload() -> dict[str, object]:
    return {
        "signal_types": list(SignalType.values),
        "capability_rules": {key: list(value) for key, value in CAPABILITY_RULES.items()},
        "term_matcher_version": "token_boundary-1.0",
        "suspicious_patterns": list(SUSPICIOUS_PATTERNS),
    }


def ensure_default_ontology() -> SignalOntology:
    payload = _ontology_payload()
    digest = _canonical_hash(payload)
    with transaction.atomic():
        ontology, created = SignalOntology.objects.get_or_create(
            version=ONTOLOGY_VERSION,
            defaults={
                "allowed_signal_types": list(SignalType.values),
                "allowed_capability_tags": sorted(CAPABILITY_RULES),
                "rule_payload": payload,
                "ontology_sha256": digest,
                "active": True,
            },
        )
        if not created and ontology.ontology_sha256 != digest:
            raise SignalValidationError(
                "The immutable signal ontology version differs from the configured rules."
            )
        SignalOntology.objects.filter(active=True).exclude(pk=ontology.pk).update(active=False)
        if not ontology.active:
            ontology.active = True
            ontology.save(update_fields=("active",))
    return ontology


def _description_segments(text: str) -> list[tuple[int, int, str]]:
    segments: list[tuple[int, int, str]] = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, flags=re.DOTALL):
        start, end = match.span()
        while start < end:
            chunk_end = min(start + MAX_EVIDENCE_TEXT, end)
            if chunk_end < end:
                split = text.rfind(" ", start, chunk_end + 1)
                if split > start:
                    chunk_end = split
            exact = text[start:chunk_end]
            if exact:
                segments.append((start, chunk_end, exact))
            start = chunk_end
            while start < end and text[start].isspace():
                start += 1
    return segments


@transaction.atomic
def build_evidence_catalog(snapshot: JobPostingSnapshot) -> EvidenceCatalog:
    existing = EvidenceCatalog.objects.filter(
        snapshot=snapshot, builder_version=EVIDENCE_BUILDER_VERSION
    ).first()
    if existing is not None:
        return cast(EvidenceCatalog, existing)
    language = str(snapshot.metadata.get("language", ""))[:16]
    raw_items: list[dict[str, object]] = [
        {
            "field_path": "title",
            "exact_text": snapshot.title,
            "normalized_text": " ".join(snapshot.title.split()).casefold(),
            "start_offset": None,
            "end_offset": None,
            "language": language,
        }
    ]
    for start, end, exact in _description_segments(snapshot.description_text):
        raw_items.append(
            {
                "field_path": "description_text",
                "exact_text": exact,
                "normalized_text": " ".join(exact.split()).casefold(),
                "start_offset": start,
                "end_offset": end,
                "language": language,
            }
        )
    materialized = []
    for ordinal, item in enumerate(raw_items, start=1):
        materialized.append(
            {
                **item,
                "public_id": f"EV-{ordinal:06d}",
                "content_sha256": hashlib.sha256(str(item["exact_text"]).encode()).hexdigest(),
            }
        )
    catalog = EvidenceCatalog.objects.create(
        snapshot=snapshot,
        builder_version=EVIDENCE_BUILDER_VERSION,
        item_count=len(materialized),
        catalog_sha256=_canonical_hash(materialized),
    )
    EvidenceItem.objects.bulk_create(
        [EvidenceItem(catalog=catalog, **item) for item in materialized]
    )
    return catalog


def _is_suspicious(item: EvidenceItem) -> bool:
    return any(pattern in item.normalized_text for pattern in SUSPICIOUS_PATTERNS)


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def _tags_for(item: EvidenceItem) -> tuple[str, ...]:
    if _is_suspicious(item):
        return ()
    return tuple(
        tag
        for tag, terms in CAPABILITY_RULES.items()
        if any(_contains_term(item.normalized_text, term) for term in terms)
    )


def _deterministic_result(
    event: PostingChangeEvent, catalog: EvidenceCatalog
) -> SignalDetectionResultV2:
    items = list(catalog.items.all())
    if event.change_type == PostingChangeType.CREATED:
        matched = [(item, _tags_for(item)) for item in items]
        matched = [(item, tags) for item, tags in matched if tags]
        if not matched:
            return SignalDetectionResultV2(
                schema_version="2.0",
                prompt_version="2.0.0",
                signals=(),
                no_signal_reason="No supported capability demand was observed.",
                unknowns=(),
            )
        tags = sorted({tag for _, item_tags in matched for tag in item_tags})
        return SignalDetectionResultV2(
            signals=(
                SignalCandidateV2(
                    signal_type="capability_hiring",
                    event_kind="created",
                    capability_tags=tuple(tags),
                    supporting_evidence_ids=tuple(item.public_id for item, _ in matched[:20]),
                    confidence=0.95,
                    concise_rationale=(
                        "The published role explicitly requests supported capability work."
                    ),
                    review_flags=(),
                ),
            ),
            schema_version="2.0",
            prompt_version="2.0.0",
            no_signal_reason=None,
            unknowns=(),
        )
    if event.change_type == PostingChangeType.MATERIAL:
        old_text: set[str] = set()
        if event.old_snapshot_id:
            old_catalog = build_evidence_catalog(cast(JobPostingSnapshot, event.old_snapshot))
            old_text = set(old_catalog.items.values_list("normalized_text", flat=True))
        matched = [
            (item, _tags_for(item))
            for item in items
            if item.normalized_text not in old_text and _tags_for(item)
        ]
        if not matched:
            return SignalDetectionResultV2(
                schema_version="2.0",
                prompt_version="2.0.0",
                signals=(),
                no_signal_reason="The material edit added no supported capability demand.",
                unknowns=(),
            )
        tags = sorted({tag for _, item_tags in matched for tag in item_tags})
        return SignalDetectionResultV2(
            signals=(
                SignalCandidateV2(
                    signal_type="material_description_change",
                    event_kind="material",
                    capability_tags=tuple(tags),
                    supporting_evidence_ids=tuple(item.public_id for item, _ in matched[:20]),
                    confidence=0.92,
                    concise_rationale=(
                        "The role description newly adds supported capability requirements."
                    ),
                    review_flags=(),
                ),
            ),
            schema_version="2.0",
            prompt_version="2.0.0",
            no_signal_reason=None,
            unknowns=(),
        )
    title = next((item for item in items if item.field_path == "title"), None)
    if title is None or _is_suspicious(title):
        return SignalDetectionResultV2(
            schema_version="2.0",
            prompt_version="2.0.0",
            signals=(),
            no_signal_reason="No safe title evidence is available for the lifecycle event.",
            unknowns=(),
        )
    signal_type: Literal["role_closed", "role_reopened"]
    event_kind: Literal["closed", "reopened"]
    if event.change_type == PostingChangeType.CLOSED:
        signal_type = "role_closed"
        event_kind = "closed"
        rationale = "The source-backed role was observed as closed."
    elif event.change_type == PostingChangeType.REOPENED:
        signal_type = "role_reopened"
        event_kind = "reopened"
        rationale = "The previously closed source-backed role was observed open again."
    else:
        return SignalDetectionResultV2(
            schema_version="2.0",
            prompt_version="2.0.0",
            signals=(),
            no_signal_reason="This change type is not eligible for signal detection.",
            unknowns=(),
        )
    return SignalDetectionResultV2(
        signals=(
            SignalCandidateV2(
                signal_type=signal_type,
                event_kind=event_kind,
                capability_tags=(),
                supporting_evidence_ids=(title.public_id,),
                confidence=1.0,
                concise_rationale=rationale,
                review_flags=(),
            ),
        ),
        schema_version="2.0",
        prompt_version="2.0.0",
        no_signal_reason=None,
        unknowns=(),
    )


def validate_detection_result(
    *,
    event: PostingChangeEvent,
    catalog: EvidenceCatalog,
    ontology: SignalOntology,
    result: SignalDetectionResultV2,
) -> list[tuple[SignalCandidateV2, tuple[EvidenceItem, ...]]]:
    if catalog.snapshot_id != event.new_snapshot_id:
        raise SignalValidationError("Evidence catalog does not belong to the event snapshot.")
    allowed_types = set(ontology.allowed_signal_types)
    allowed_tags = set(ontology.allowed_capability_tags)
    compatible_types: set[str] = {
        "created": {"capability_hiring"},
        "material": {"material_description_change"},
        "reopened": {"role_reopened", "role_reposted"},
        "closed": {"role_closed"},
    }.get(event.change_type, set())
    item_map = {item.public_id: item for item in catalog.items.all()}
    validated: list[tuple[SignalCandidateV2, tuple[EvidenceItem, ...]]] = []
    for candidate in result.signals:
        if (
            candidate.signal_type not in allowed_types
            or candidate.signal_type not in compatible_types
        ):
            raise SignalValidationError("Signal type is not compatible with the observed event.")
        if not set(candidate.capability_tags).issubset(allowed_tags):
            raise SignalValidationError("Signal contains an unknown capability tag.")
        if candidate.event_kind != event.change_type:
            raise SignalValidationError("Signal event kind does not match the observed event.")
        if any(term in candidate.concise_rationale.casefold() for term in COMMERCIAL_TERMS):
            raise SignalValidationError("Signal rationale crosses the observational boundary.")
        if len(set(candidate.supporting_evidence_ids)) != len(candidate.supporting_evidence_ids):
            raise SignalValidationError("Signal repeats an evidence reference.")
        try:
            evidence = tuple(item_map[item_id] for item_id in candidate.supporting_evidence_ids)
        except KeyError as exc:
            raise SignalValidationError("Signal references evidence outside this catalog.") from exc
        if any(_is_suspicious(item) for item in evidence):
            raise SignalValidationError("Signal references instruction-like untrusted text.")
        validated.append((candidate, evidence))
    return validated


@transaction.atomic
def schedule_signal_detection(
    event: PostingChangeEvent,
    *,
    trigger: str | None = None,
) -> ScheduledDetection | None:
    if event.change_type not in ELIGIBLE_CHANGE_TYPES or event.new_snapshot_id is None:
        return None
    ontology = ensure_default_ontology()
    run_key = f"signals.detect:{event.pk}:{DETECTOR_VERSION}:{ontology.version}"
    run, created = PipelineRun.objects.get_or_create(
        idempotency_key=run_key,
        defaults={
            "pipeline_name": "signals.detection",
            "stage": "detection_queued",
            "status": PipelineStatus.QUEUED,
            "trigger": trigger or event.parse_run.trigger,
            "requested_by": event.parse_run.requested_by,
            "request_id": event.parse_run.request_id,
            "object_type": "posting_change_event",
            "object_id": event.pk,
            "heartbeat_at": timezone.now(),
            "input_count": 1,
            "policy_versions": {
                "detector": DETECTOR_VERSION,
                "ontology": ontology.version,
                "prompt": PROMPT_VERSION,
                "schema": SCHEMA_VERSION,
            },
            "context": {
                "posting_id": str(event.posting_id),
                "job_snapshot_id": str(event.new_snapshot_id),
                "change_type": event.change_type,
            },
        },
    )
    attempt, _ = SignalDetectionAttempt.objects.get_or_create(
        pipeline_run=run,
        defaults={
            "change_event": event,
            "ontology": ontology,
            "status": DetectionStatus.QUEUED,
            "detector_method": DetectionMethod.DETERMINISTIC,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "detector_version": DETECTOR_VERSION,
        },
    )
    payload = TargetCommandPayloadV1(pipeline_run_id=run.pk, object_id=event.pk)
    outbox, outbox_created = TaskOutbox.objects.get_or_create(
        idempotency_key=f"signals.detect-command:{event.pk}:{DETECTOR_VERSION}",
        defaults={
            "command_type": SIGNALS_DETECT_COMMAND_TYPE,
            "payload": payload.model_dump(mode="json"),
            "payload_schema_version": "1.0",
            "pipeline_run": run,
            "request_id": run.request_id,
        },
    )
    if outbox_created:
        outbox.full_clean()
    return ScheduledDetection(run=run, attempt=attempt, outbox=outbox, created=created)


@transaction.atomic
def execute_signal_detection(envelope: TaskEnvelopeV2) -> bool:
    if envelope.command_type != SIGNALS_DETECT_COMMAND_TYPE:
        raise ValueError("Unsupported signal-detection command type.")
    run = PipelineRun.objects.select_for_update().get(pk=envelope.pipeline_run_id)
    if run.object_id != envelope.object_id:
        raise ValueError("Envelope object does not match its signal-detection run.")
    outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=run)
    if outbox.idempotency_key != envelope.idempotency_key:
        raise ValueError("Envelope idempotency does not match the signal command.")
    effect_key = f"{envelope.idempotency_key}:effect"
    if PipelineStepRun.objects.filter(idempotency_key=effect_key).exists():
        return False
    attempt = (
        SignalDetectionAttempt.objects.select_for_update(of=("self",))
        .select_related("change_event__new_snapshot", "change_event__posting__company", "ontology")
        .get(pipeline_run=run)
    )
    now = timezone.now()
    attempt.status = DetectionStatus.RUNNING
    attempt.started_at = attempt.started_at or now
    attempt.save(update_fields=("status", "started_at"))
    run.status = PipelineStatus.RUNNING
    run.stage = "deterministic_detection"
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
    event = attempt.change_event
    if event.new_snapshot is None:
        raise SignalValidationError("Eligible signal event has no normalized snapshot.")
    catalog = build_evidence_catalog(event.new_snapshot)
    result = _deterministic_result(event, catalog)
    validated = validate_detection_result(
        event=event, catalog=catalog, ontology=attempt.ontology, result=result
    )
    input_payload = {
        "change_event_id": str(event.pk),
        "change_type": event.change_type,
        "snapshot_id": str(event.new_snapshot_id),
        "catalog_sha256": catalog.catalog_sha256,
        "ontology_sha256": attempt.ontology.ontology_sha256,
    }
    signal_ids: list[str] = []
    for candidate, evidence in validated:
        signal, _ = SignalEvent.objects.get_or_create(
            idempotency_key=(
                f"signals.event:{event.pk}:{candidate.signal_type}:"
                f"{DETECTOR_VERSION}:{attempt.ontology.version}"
            ),
            defaults={
                "company": event.posting.company,
                "posting": event.posting,
                "change_event": event,
                "detection_attempt": attempt,
                "signal_type": candidate.signal_type,
                "event_kind": event.change_type,
                "capability_tags": list(candidate.capability_tags),
                "confidence": Decimal(str(candidate.confidence)),
                "rationale": candidate.concise_rationale,
                "occurred_at": event.occurred_at,
                "observed_at": event.created_at,
                "ontology_version": attempt.ontology.version,
                "prompt_version": PROMPT_VERSION,
                "schema_version": SCHEMA_VERSION,
                "detector_version": DETECTOR_VERSION,
            },
        )
        SignalEvidence.objects.bulk_create(
            [SignalEvidence(signal=signal, evidence_item=item) for item in evidence],
            ignore_conflicts=True,
        )
        signal_ids.append(str(signal.pk))
    completed = timezone.now()
    prior_signals = (
        SignalEvent.objects.select_for_update()
        .filter(
            change_event=event,
            status=SignalStatus.ACTIVE,
        )
        .exclude(detection_attempt=attempt)
    )
    for prior in prior_signals:
        prior.status = SignalStatus.RETRACTED
        prior.review_state = SignalReviewState.SUPERSEDED
        prior.reviewed_at = completed
        prior.review_reason = (
            f"Superseded by detector {DETECTOR_VERSION} / ontology {attempt.ontology.version}."
        )
        prior.save(update_fields=("status", "review_state", "reviewed_at", "review_reason"))
        AuditEvent.objects.create(
            actor_type=ActorType.SYSTEM,
            action="signals.detector_result_superseded",
            object_type="signal_event",
            object_id=prior.pk,
            before_summary={"status": SignalStatus.ACTIVE},
            after_summary={
                "status": SignalStatus.RETRACTED,
                "review_state": SignalReviewState.SUPERSEDED,
                "replacement_signal_ids": signal_ids,
            },
            reason_key="newer_detector_policy_completed",
            request_id=run.request_id,
            pipeline_run=run,
        )
    attempt.evidence_catalog = catalog
    attempt.status = DetectionStatus.COMPLETE if validated else DetectionStatus.NO_SIGNAL
    attempt.input_sha256 = _canonical_hash(input_payload)
    attempt.output_payload = result.model_dump(mode="json")
    attempt.no_signal_reason = result.no_signal_reason or ""
    attempt.completed_at = completed
    attempt.save(
        update_fields=(
            "evidence_catalog",
            "status",
            "input_sha256",
            "output_payload",
            "no_signal_reason",
            "completed_at",
        )
    )
    PipelineStepRun.objects.create(
        pipeline_run=run,
        stage="signal_detection",
        status=StepStatus.COMPLETE,
        idempotency_key=effect_key,
        started_at=attempt.started_at,
        heartbeat_at=completed,
        completed_at=completed,
        input_ids=input_payload,
        output_ids={"signal_ids": signal_ids, "evidence_catalog_id": str(catalog.pk)},
    )
    run.stage = "detection_complete" if validated else "no_signal"
    run.status = PipelineStatus.COMPLETE
    run.completed_at = completed
    run.heartbeat_at = completed
    run.output_count = len(validated)
    run.row_version += 1
    run.save(
        update_fields=(
            "stage",
            "status",
            "completed_at",
            "heartbeat_at",
            "output_count",
            "row_version",
            "updated_at",
        )
    )
    AuditEvent.objects.create(
        actor_type=ActorType.SYSTEM,
        action="signals.detection_completed",
        object_type="posting_change_event",
        object_id=event.pk,
        before_summary={},
        after_summary={
            "status": attempt.status,
            "signal_ids": signal_ids,
            "catalog_id": str(catalog.pk),
        },
        reason_key="observed_change_processed",
        request_id=run.request_id,
        pipeline_run=run,
    )
    from apps.signals.classification import schedule_signal_classification

    for signal_id in signal_ids:
        schedule_signal_classification(SignalEvent.objects.get(pk=signal_id))
    return True


@transaction.atomic
def mark_detection_failed(*, pipeline_run_id: UUID, error: Exception) -> None:
    run = PipelineRun.objects.select_for_update().get(pk=pipeline_run_id)
    attempt = SignalDetectionAttempt.objects.select_for_update().get(pipeline_run=run)
    if attempt.status in {DetectionStatus.COMPLETE, DetectionStatus.NO_SIGNAL}:
        return
    message = (str(error).replace("\n", " ").strip() or error.__class__.__name__)[:500]
    code = (
        "SIGNAL_VALIDATION_FAILED"
        if isinstance(error, SignalValidationError)
        else "SIGNAL_DETECTION_FAILED"
    )
    now = timezone.now()
    attempt.status = DetectionStatus.FAILED
    attempt.error_code = code
    attempt.safe_error_message = message
    attempt.completed_at = now
    attempt.save(
        update_fields=(
            "status",
            "error_code",
            "safe_error_message",
            "completed_at",
        )
    )
    run.status = PipelineStatus.FAILED
    run.stage = "detection_failed"
    run.completed_at = now
    run.heartbeat_at = now
    run.error_count = 1
    run.last_error_code = code
    run.last_error_message = message
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
    AuditEvent.objects.create(
        actor_type=ActorType.SYSTEM,
        action="signals.detection_failed",
        object_type="posting_change_event",
        object_id=attempt.change_event_id,
        before_summary={},
        after_summary={"status": DetectionStatus.FAILED, "error_code": code},
        reason_key=code.casefold(),
        request_id=run.request_id,
        pipeline_run=run,
    )


@transaction.atomic
def retract_signal(
    *, signal_id: UUID, actor: User, reason: str, request_id: UUID | None
) -> SignalEvent:
    normalized_reason = " ".join(reason.split())[:500]
    if len(normalized_reason) < 5:
        raise SignalValidationError("Retraction reason must be at least five characters.")
    signal = SignalEvent.objects.select_for_update().get(pk=signal_id)
    if signal.status == SignalStatus.RETRACTED:
        return signal
    before = {"status": signal.status, "review_state": signal.review_state}
    signal.status = SignalStatus.RETRACTED
    signal.review_state = SignalReviewState.FALSE_POSITIVE
    signal.reviewed_by = actor
    signal.reviewed_at = timezone.now()
    signal.review_reason = normalized_reason
    signal.save(
        update_fields=(
            "status",
            "review_state",
            "reviewed_by",
            "reviewed_at",
            "review_reason",
        )
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="signals.false_positive_retracted",
        object_type="signal_event",
        object_id=signal.pk,
        before_summary=before,
        after_summary={"status": signal.status, "review_state": signal.review_state},
        reason_key=normalized_reason,
        request_id=request_id,
        pipeline_run=signal.detection_attempt.pipeline_run,
    )
    from apps.opportunities.services import schedule_company_aggregation

    assessment = signal.assessments.filter(status=AssessmentStatus.COMPLETED).first()
    if assessment is not None:
        schedule_company_aggregation(
            signal.company,
            trigger_assessment=assessment,
            cause_key=f"signal-retraction:{signal.pk}:{signal.reviewed_at.isoformat()}",
        )
    return signal
