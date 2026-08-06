from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import cast
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.operations.commands import SIGNALS_CLASSIFY_COMMAND_TYPE
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
from apps.signals.assessment_contracts import (
    CapabilityAssessmentV2,
    CapabilityClusterV2,
    CapabilityGapV2,
    CategoricalJudgmentV2,
    ComponentJudgmentsV2,
    NumericJudgmentV2,
)
from apps.signals.models import (
    AssessmentOverride,
    AssessmentStatus,
    CapabilityClusterRecord,
    CapabilityGapRecord,
    OpportunityMode,
    SignalAssessment,
    SignalAssessmentEvidence,
    SignalEvent,
    SignalStatus,
)

CLASSIFIER_VERSION = "1.0.0"
SCORING_POLICY_VERSION = "2.0.0"
PROMPT_VERSION = "2.1.0"
SCHEMA_VERSION = "2.1"

TAG_CLUSTER_MAP = {
    "creative_ai_production": "creative_ai_pipeline",
    "learning_content": "learning_system",
    "workflow_automation": "workflow_design",
    "knowledge_systems": "knowledge_architecture",
    "ai_enablement": "enablement_and_adoption",
    "data_integration": "integration_architecture",
    "local_private_ai": "private_ai_infrastructure",
}
TAG_GAP_MAP = {
    "creative_ai_production": "repeatable_creative_production",
    "learning_content": "scalable_learning_content_operations",
    "workflow_automation": "governed_workflow_automation",
    "knowledge_systems": "retrievable_organizational_knowledge",
    "ai_enablement": "responsible_ai_adoption",
    "data_integration": "reliable_system_integration",
    "local_private_ai": "private_ai_runtime_and_governance",
}
TAG_LAYER_MAP = {
    "creative_ai_production": ("create", "build"),
    "learning_content": ("create", "enable"),
    "workflow_automation": ("build", "deploy"),
    "knowledge_systems": ("build", "deploy"),
    "ai_enablement": ("enable",),
    "data_integration": ("build", "deploy"),
    "local_private_ai": ("deploy",),
}
SYSTEM_BUILDING_TAGS = {
    "workflow_automation",
    "knowledge_systems",
    "data_integration",
    "local_private_ai",
}
SCORE_WEIGHTS = {
    "task_overlap": Decimal("0.25"),
    "ftl_capability_overlap": Decimal("0.20"),
    "reusable_system_potential": Decimal("0.15"),
    "infrastructure_work_potential": Decimal("0.10"),
    "enablement_potential": Decimal("0.10"),
    "portfolio_proof_availability": Decimal("0.10"),
    "industry_strategic_relevance": Decimal("0.10"),
}


class AssessmentValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ScheduledAssessment:
    run: PipelineRun
    assessment: SignalAssessment
    outbox: TaskOutbox
    created: bool


def _canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _mode_for(signal: SignalEvent) -> tuple[str, float, str]:
    tags = set(signal.capability_tags)
    if not tags:
        return (
            OpportunityMode.WATCH_SIGNAL,
            0.96,
            "The observed lifecycle event has no supported capability scope to classify.",
        )
    if tags & SYSTEM_BUILDING_TAGS or len(tags) >= 2:
        return (
            OpportunityMode.HYBRID,
            0.72,
            "The posting supports internal hiring while its system-building scope makes a "
            "bounded external contribution plausible; vendor receptivity remains unknown.",
        )
    return (
        OpportunityMode.EMPLOYMENT_ONLY,
        0.82,
        "The current evidence supports an internal hiring need but not an external-service route.",
    )


def _deterministic_assessment(signal: SignalEvent) -> CapabilityAssessmentV2:
    evidence_ids = tuple(
        signal.evidence_links.order_by("evidence_item__public_id").values_list(
            "evidence_item__public_id", flat=True
        )
    )
    if not evidence_ids:
        raise AssessmentValidationError("A signal assessment requires exact supporting evidence.")
    tags = tuple(sorted(set(signal.capability_tags)))
    unsupported = set(tags) - set(TAG_CLUSTER_MAP)
    if unsupported:
        raise AssessmentValidationError(
            "Signal contains capability tags outside classifier policy."
        )
    mode, mode_confidence, mode_rationale = _mode_for(signal)
    clusters = tuple(
        CapabilityClusterV2(key=TAG_CLUSTER_MAP[tag], confidence=0.92, evidence_ids=evidence_ids)
        for tag in tags
    )
    gaps = tuple(
        CapabilityGapV2(
            key=TAG_GAP_MAP[tag],
            confidence=0.68,
            evidence_ids=evidence_ids,
            concise_rationale=(
                "The source-backed role scope plausibly indicates a capability gap; "
                "company research is still required."
            ),
        )
        for tag in tags
    )
    ordered_layers = ("create", "build", "deploy", "enable")
    selected_layers = {layer for tag in tags for layer in TAG_LAYER_MAP.get(tag, ())}
    task_score = min(96, 72 + 6 * len(tags)) if tags else 25
    reusable_score = 82 if set(tags) & SYSTEM_BUILDING_TAGS else (58 if tags else 20)
    enablement_score = 84 if set(tags) & {"ai_enablement", "learning_content"} else 52
    if "local_private_ai" in tags:
        infrastructure = "high"
    elif set(tags) & {"data_integration", "workflow_automation", "knowledge_systems"}:
        infrastructure = "medium"
    else:
        infrastructure = "low" if tags else "unknown"
    unknowns = [
        "Vendor or partner receptivity is not established by a job posting.",
        "Portfolio-proof availability requires the versioned FTL asset catalog.",
    ]
    if signal.company.strategic_fit_manual is None:
        unknowns.append("Industry and strategic relevance has not been set by FTL policy.")
    return CapabilityAssessmentV2.model_validate(
        {
            "schema_version": "2.1",
            "prompt_version": "2.1.0",
            "capability_clusters": clusters,
            "capability_gaps": gaps,
            "opportunity_mode": mode,
            "mode_confidence": mode_confidence,
            "mode_evidence_ids": evidence_ids,
            "mode_rationale": mode_rationale,
            "recommended_ftl_layers": tuple(
                layer for layer in ordered_layers if layer in selected_layers
            ),
            "entry_offer_candidates": (),
            "component_judgments": ComponentJudgmentsV2(
                task_overlap=NumericJudgmentV2(score=task_score, confidence=0.93),
                reusable_system_potential=NumericJudgmentV2(score=reusable_score, confidence=0.76),
                enablement_potential=NumericJudgmentV2(score=enablement_score, confidence=0.65),
                infrastructure_relevance=CategoricalJudgmentV2.model_validate(
                    {"value": infrastructure, "confidence": 0.72 if tags else 0.3}
                ),
                vendor_receptivity=CategoricalJudgmentV2(value="unknown", confidence=0.0),
            ),
            "unknowns": tuple(unknowns),
            "review_flags": (),
        }
    )


def _score_components(
    signal: SignalEvent, result: CapabilityAssessmentV2
) -> tuple[dict[str, int | None], dict[str, float], list[str], int, Decimal]:
    judgments = result.component_judgments
    categorical = {"low": 30, "medium": 60, "high": 85, "unknown": None}
    values: dict[str, int | None] = {
        "task_overlap": judgments.task_overlap.score,
        "ftl_capability_overlap": min(100, 65 + 8 * len(result.capability_clusters))
        if result.capability_clusters
        else 20,
        "reusable_system_potential": judgments.reusable_system_potential.score,
        "infrastructure_work_potential": categorical[judgments.infrastructure_relevance.value],
        "enablement_potential": judgments.enablement_potential.score,
        "portfolio_proof_availability": None,
        "industry_strategic_relevance": signal.company.strategic_fit_manual,
    }
    confidence = {
        "task_overlap": judgments.task_overlap.confidence,
        "ftl_capability_overlap": 1.0,
        "reusable_system_potential": judgments.reusable_system_potential.confidence,
        "infrastructure_work_potential": judgments.infrastructure_relevance.confidence,
        "enablement_potential": judgments.enablement_potential.confidence,
        "portfolio_proof_availability": 0.0,
        "industry_strategic_relevance": 1.0
        if signal.company.strategic_fit_manual is not None
        else 0.0,
    }
    known_weight = sum(
        (weight for key, weight in SCORE_WEIGHTS.items() if values[key] is not None),
        Decimal("0"),
    )
    coverage = known_weight / sum(SCORE_WEIGHTS.values(), Decimal("0"))
    weighted = (
        sum(
            Decimal(cast(int, values[key])) * weight
            for key, weight in SCORE_WEIGHTS.items()
            if values[key] is not None
        )
        / known_weight
    )
    penalized = weighted * (Decimal("0.85") + Decimal("0.15") * coverage)
    score = int(penalized.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    missing = [key for key, value in values.items() if value is None]
    return values, confidence, missing, score, coverage.quantize(Decimal("0.001"))


def _input_payload(signal: SignalEvent) -> dict[str, object]:
    evidence = list(
        signal.evidence_links.order_by("evidence_item__public_id").values_list(
            "evidence_item__public_id", "evidence_item__content_sha256"
        )
    )
    return {
        "signal_id": str(signal.pk),
        "signal_type": signal.signal_type,
        "capability_tags": sorted(signal.capability_tags),
        "evidence": evidence,
        "ontology_version": signal.ontology_version,
        "classifier_version": CLASSIFIER_VERSION,
        "scoring_policy_version": SCORING_POLICY_VERSION,
    }


@transaction.atomic
def schedule_signal_classification(signal: SignalEvent) -> ScheduledAssessment | None:
    if signal.status != SignalStatus.ACTIVE:
        return None
    run_key = f"signals.classify:{signal.pk}:{CLASSIFIER_VERSION}:{SCORING_POLICY_VERSION}"
    detection_run = signal.detection_attempt.pipeline_run
    run, created = PipelineRun.objects.get_or_create(
        idempotency_key=run_key,
        defaults={
            "pipeline_name": "signals.classification",
            "stage": "classification_queued",
            "status": PipelineStatus.QUEUED,
            "trigger": detection_run.trigger,
            "requested_by": detection_run.requested_by,
            "request_id": detection_run.request_id,
            "object_type": "signal_event",
            "object_id": signal.pk,
            "heartbeat_at": timezone.now(),
            "input_count": 1,
            "policy_versions": {
                "classifier": CLASSIFIER_VERSION,
                "ontology": signal.ontology_version,
                "scoring": SCORING_POLICY_VERSION,
                "prompt": PROMPT_VERSION,
                "schema": SCHEMA_VERSION,
            },
        },
    )
    input_sha256 = _canonical_hash(_input_payload(signal))
    assessment, _ = SignalAssessment.objects.get_or_create(
        pipeline_run=run,
        defaults={
            "signal": signal,
            "status": AssessmentStatus.QUEUED,
            "ontology_version": signal.ontology_version,
            "scoring_policy_version": SCORING_POLICY_VERSION,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "opportunity_mode": OpportunityMode.UNKNOWN,
            "mode_confidence": Decimal("0"),
            "mode_rationale": "Pending deterministic classification.",
            "confidence": Decimal("0"),
            "input_sha256": input_sha256,
            "idempotency_key": run_key,
        },
    )
    payload = TargetCommandPayloadV1(pipeline_run_id=run.pk, object_id=signal.pk)
    outbox, outbox_created = TaskOutbox.objects.get_or_create(
        idempotency_key=f"signals.classify-command:{signal.pk}:{CLASSIFIER_VERSION}",
        defaults={
            "command_type": SIGNALS_CLASSIFY_COMMAND_TYPE,
            "payload": payload.model_dump(mode="json"),
            "payload_schema_version": "1.0",
            "pipeline_run": run,
            "request_id": run.request_id,
        },
    )
    if outbox_created:
        outbox.full_clean()
    return ScheduledAssessment(run=run, assessment=assessment, outbox=outbox, created=created)


@transaction.atomic
def execute_signal_classification(envelope: TaskEnvelopeV2) -> bool:
    if envelope.command_type != SIGNALS_CLASSIFY_COMMAND_TYPE:
        raise ValueError("Unsupported signal-classification command type.")
    run = PipelineRun.objects.select_for_update().get(pk=envelope.pipeline_run_id)
    if run.object_id != envelope.object_id:
        raise ValueError("Envelope object does not match its classification run.")
    outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=run)
    if outbox.idempotency_key != envelope.idempotency_key:
        raise ValueError("Envelope idempotency does not match the classification command.")
    effect_key = f"{envelope.idempotency_key}:effect"
    if PipelineStepRun.objects.filter(idempotency_key=effect_key).exists():
        return False
    assessment = (
        SignalAssessment.objects.select_for_update()
        .select_related("signal__company", "signal__detection_attempt__pipeline_run")
        .prefetch_related("signal__evidence_links__evidence_item")
        .get(pipeline_run=run)
    )
    now = timezone.now()
    if assessment.signal.status != SignalStatus.ACTIVE:
        assessment.status = AssessmentStatus.SUPERSEDED
        assessment.completed_at = now
        assessment.save(update_fields=("status", "completed_at"))
        run.status = PipelineStatus.COMPLETE
        run.stage = "classification_superseded"
        run.completed_at = now
        run.heartbeat_at = now
        run.row_version += 1
        run.save(
            update_fields=(
                "status",
                "stage",
                "completed_at",
                "heartbeat_at",
                "row_version",
                "updated_at",
            )
        )
        PipelineStepRun.objects.create(
            pipeline_run=run,
            stage="signal_classification",
            status=StepStatus.COMPLETE,
            idempotency_key=effect_key,
            started_at=now,
            heartbeat_at=now,
            completed_at=now,
            input_ids={"signal_id": str(assessment.signal_id)},
            output_ids={"superseded": True},
        )
        return True
    assessment.status = AssessmentStatus.RUNNING
    assessment.started_at = assessment.started_at or now
    assessment.save(update_fields=("status", "started_at"))
    run.status = PipelineStatus.RUNNING
    run.stage = "deterministic_classification"
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
    result = _deterministic_assessment(assessment.signal)
    available_ids = {
        link.evidence_item.public_id: link.evidence_item
        for link in assessment.signal.evidence_links.all()
    }
    referenced_ids = set(result.mode_evidence_ids)
    for cluster in result.capability_clusters:
        referenced_ids.update(cluster.evidence_ids)
    for gap in result.capability_gaps:
        referenced_ids.update(gap.evidence_ids)
    if not referenced_ids.issubset(available_ids):
        raise AssessmentValidationError("Classification references evidence outside the signal.")
    values, coverage_map, missing, score, score_coverage = _score_components(
        assessment.signal, result
    )
    completed = timezone.now()
    assessment.status = AssessmentStatus.COMPLETED
    assessment.structured_output = result.model_dump(mode="json")
    assessment.component_values = values
    assessment.component_coverage = coverage_map
    assessment.missing_components = missing
    assessment.capability_relevance = score
    assessment.score_coverage = score_coverage
    assessment.opportunity_mode = result.opportunity_mode
    assessment.mode_confidence = Decimal(str(result.mode_confidence))
    assessment.mode_rationale = result.mode_rationale
    assessment.confidence = Decimal(str(min(coverage_map.values())))
    assessment.completed_at = completed
    assessment.save()
    CapabilityClusterRecord.objects.bulk_create(
        [
            CapabilityClusterRecord(
                assessment=assessment,
                cluster_key=cluster.key,
                confidence=Decimal(str(cluster.confidence)),
                evidence_ids=list(cluster.evidence_ids),
            )
            for cluster in result.capability_clusters
        ],
        ignore_conflicts=True,
    )
    CapabilityGapRecord.objects.bulk_create(
        [
            CapabilityGapRecord(
                assessment=assessment,
                gap_key=gap.key,
                confidence=Decimal(str(gap.confidence)),
                rationale=gap.concise_rationale,
                evidence_ids=list(gap.evidence_ids),
            )
            for gap in result.capability_gaps
        ],
        ignore_conflicts=True,
    )
    SignalAssessmentEvidence.objects.bulk_create(
        [
            SignalAssessmentEvidence(assessment=assessment, evidence_item=available_ids[item_id])
            for item_id in sorted(referenced_ids)
        ],
        ignore_conflicts=True,
    )
    prior = (
        SignalAssessment.objects.select_for_update()
        .filter(signal=assessment.signal, status=AssessmentStatus.COMPLETED)
        .exclude(pk=assessment.pk)
    )
    prior_ids = [str(value) for value in prior.values_list("pk", flat=True)]
    prior.update(status=AssessmentStatus.SUPERSEDED)
    input_payload = _input_payload(assessment.signal)
    PipelineStepRun.objects.create(
        pipeline_run=run,
        stage="signal_classification",
        status=StepStatus.COMPLETE,
        idempotency_key=effect_key,
        started_at=assessment.started_at,
        heartbeat_at=completed,
        completed_at=completed,
        input_ids=input_payload,
        output_ids={"assessment_id": str(assessment.pk), "superseded_ids": prior_ids},
    )
    run.status = PipelineStatus.COMPLETE
    run.stage = "classification_complete"
    run.completed_at = completed
    run.heartbeat_at = completed
    run.output_count = 1
    run.row_version += 1
    run.save(
        update_fields=(
            "status",
            "stage",
            "completed_at",
            "heartbeat_at",
            "output_count",
            "row_version",
            "updated_at",
        )
    )
    AuditEvent.objects.create(
        actor_type=ActorType.SYSTEM,
        action="signals.classification_completed",
        object_type="signal_assessment",
        object_id=assessment.pk,
        before_summary={},
        after_summary={
            "status": AssessmentStatus.COMPLETED,
            "capability_relevance": score,
            "coverage": str(score_coverage),
            "opportunity_mode": result.opportunity_mode,
        },
        reason_key="evidence_bound_deterministic_classification",
        request_id=run.request_id,
        pipeline_run=run,
    )
    from apps.opportunities.services import schedule_company_aggregation

    schedule_company_aggregation(assessment.signal.company, trigger_assessment=assessment)
    return True


@transaction.atomic
def mark_classification_failed(*, pipeline_run_id: UUID, error: Exception) -> None:
    run = PipelineRun.objects.select_for_update().get(pk=pipeline_run_id)
    assessment = SignalAssessment.objects.select_for_update().get(pipeline_run=run)
    if assessment.status in {AssessmentStatus.COMPLETED, AssessmentStatus.SUPERSEDED}:
        return
    message = (str(error).replace("\n", " ").strip() or error.__class__.__name__)[:500]
    code = (
        "ASSESSMENT_VALIDATION_FAILED"
        if isinstance(error, AssessmentValidationError)
        else "SIGNAL_CLASSIFICATION_FAILED"
    )
    now = timezone.now()
    assessment.status = AssessmentStatus.FAILED
    assessment.error_code = code
    assessment.safe_error_message = message
    assessment.completed_at = now
    assessment.save(update_fields=("status", "error_code", "safe_error_message", "completed_at"))
    run.status = PipelineStatus.FAILED
    run.stage = "classification_failed"
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
        action="signals.classification_failed",
        object_type="signal_assessment",
        object_id=assessment.pk,
        before_summary={},
        after_summary={"status": AssessmentStatus.FAILED, "error_code": code},
        reason_key=code.casefold(),
        request_id=run.request_id,
        pipeline_run=run,
    )


@transaction.atomic
def override_assessment_mode(
    *, assessment_id: UUID, actor: User, opportunity_mode: str, reason: str, request_id: UUID | None
) -> AssessmentOverride:
    normalized_reason = " ".join(reason.split())[:500]
    if opportunity_mode not in OpportunityMode.values:
        raise AssessmentValidationError("Unknown opportunity mode.")
    if len(normalized_reason) < 5:
        raise AssessmentValidationError("Override reason must be at least five characters.")
    assessment = (
        SignalAssessment.objects.select_for_update()
        .select_related("signal__company", "pipeline_run")
        .get(pk=assessment_id)
    )
    if assessment.status != AssessmentStatus.COMPLETED:
        raise AssessmentValidationError("Only a current completed assessment can be overridden.")
    override = AssessmentOverride.objects.create(
        assessment=assessment,
        opportunity_mode=opportunity_mode,
        actor=actor,
        reason=normalized_reason,
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="signals.assessment_mode_overridden",
        object_type="signal_assessment",
        object_id=assessment.pk,
        before_summary={"opportunity_mode": assessment.opportunity_mode},
        after_summary={"opportunity_mode": opportunity_mode, "override_id": str(override.pk)},
        reason_key=normalized_reason,
        request_id=request_id,
        pipeline_run=assessment.pipeline_run,
    )
    from apps.opportunities.services import schedule_company_aggregation

    schedule_company_aggregation(
        assessment.signal.company,
        trigger_assessment=assessment,
        cause_key=f"assessment-override:{override.pk}",
    )
    return override
