from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean
from typing import Any, cast
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.companies.models import Company, CompanyMergeReview, CompanyStatus, MergeReviewState
from apps.jobs.models import PostingLifecycle
from apps.operations.commands import COMPANIES_AGGREGATE_COMMAND_TYPE
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
from apps.opportunities.models import (
    CompanyAssessment,
    CompanyFeature,
    CompanyPattern,
    DerivedStatus,
    Opportunity,
    OpportunitySignal,
    PatternKey,
    QualificationOverride,
    QualificationStatus,
)
from apps.signals.models import AssessmentStatus, OpportunityMode, SignalAssessment, SignalStatus
from apps.sources.models import EndpointStatus

FEATURE_BUILDER_VERSION = "2.0.0"
PATTERN_RULE_VERSION = "2.0.0"
SCORING_POLICY_VERSION = "2.0.0"
USE_CASE_FAMILY = "capability_systems"
MIN_RESEARCH_SCORE = 55
MIN_RESEARCH_COVERAGE = Decimal("0.400")
COMPANY_SCORE_WEIGHTS = {
    "capability_relevance": Decimal("0.40"),
    "commercial_actionability": Decimal("0.25"),
    "long_term_system_potential": Decimal("0.20"),
    "strategic_value": Decimal("0.15"),
}


class AggregationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ScheduledAggregation:
    run: PipelineRun
    outbox: TaskOutbox
    created: bool


@dataclass(frozen=True)
class ScoreValue:
    score: int | None
    coverage: Decimal
    missing: tuple[str, ...]


def _canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _rounded(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _normalized_score(values: dict[str, int | None]) -> ScoreValue:
    known = [Decimal(value) for value in values.values() if value is not None]
    if not known:
        return ScoreValue(None, Decimal("0.000"), tuple(values))
    coverage = (Decimal(len(known)) / Decimal(len(values))).quantize(Decimal("0.001"))
    raw = sum(known) / Decimal(len(known))
    penalized = raw * (Decimal("0.85") + Decimal("0.15") * coverage)
    return ScoreValue(
        _rounded(penalized),
        coverage,
        tuple(key for key, value in values.items() if value is None),
    )


def _priority_score(scores: dict[str, ScoreValue]) -> ScoreValue:
    known_weight = sum(
        weight for key, weight in COMPANY_SCORE_WEIGHTS.items() if scores[key].score is not None
    )
    if not known_weight:
        return ScoreValue(None, Decimal("0.000"), tuple(scores))
    raw = (
        sum(
            Decimal(cast(int, scores[key].score)) * weight
            for key, weight in COMPANY_SCORE_WEIGHTS.items()
            if scores[key].score is not None
        )
        / known_weight
    )
    coverage = sum(
        (weight * scores[key].coverage for key, weight in COMPANY_SCORE_WEIGHTS.items()),
        Decimal("0"),
    ).quantize(Decimal("0.001"))
    penalized = raw * (Decimal("0.85") + Decimal("0.15") * coverage)
    score = _rounded(penalized)
    if coverage < MIN_RESEARCH_COVERAGE:
        score = min(score, MIN_RESEARCH_SCORE - 1)
    missing = tuple(
        f"{group}.{item}" for group, result in scores.items() for item in result.missing
    )
    return ScoreValue(score, coverage, missing)


@transaction.atomic
def schedule_company_aggregation(
    company: Company,
    *,
    trigger_assessment: SignalAssessment,
    cause_key: str | None = None,
) -> ScheduledAggregation:
    cause = cause_key or str(trigger_assessment.pk)
    run_key = (
        f"companies.aggregate:{company.pk}:{cause}:"
        f"{FEATURE_BUILDER_VERSION}:{SCORING_POLICY_VERSION}"
    )
    upstream = trigger_assessment.pipeline_run
    run, created = PipelineRun.objects.get_or_create(
        idempotency_key=run_key,
        defaults={
            "pipeline_name": "companies.aggregation",
            "stage": "aggregation_queued",
            "status": PipelineStatus.QUEUED,
            "trigger": upstream.trigger,
            "requested_by": upstream.requested_by,
            "request_id": upstream.request_id,
            "object_type": "company",
            "object_id": company.pk,
            "heartbeat_at": timezone.now(),
            "input_count": 1,
            "policy_versions": {
                "features": FEATURE_BUILDER_VERSION,
                "patterns": PATTERN_RULE_VERSION,
                "scoring": SCORING_POLICY_VERSION,
            },
            "context": {
                "trigger_assessment_id": str(trigger_assessment.pk),
                "cause_key": cause,
            },
        },
    )
    payload = TargetCommandPayloadV1(pipeline_run_id=run.pk, object_id=company.pk)
    outbox, outbox_created = TaskOutbox.objects.get_or_create(
        idempotency_key=(
            f"companies.aggregate-command:{company.pk}:{cause}:{FEATURE_BUILDER_VERSION}"
        ),
        defaults={
            "command_type": COMPANIES_AGGREGATE_COMMAND_TYPE,
            "payload": payload.model_dump(mode="json"),
            "payload_schema_version": "1.0",
            "pipeline_run": run,
            "request_id": run.request_id,
        },
    )
    if outbox_created:
        outbox.full_clean()
    return ScheduledAggregation(run=run, outbox=outbox, created=created)


def _seniority(title: str) -> str:
    normalized = title.casefold()
    if any(term in normalized for term in ("head", "director", "vp", "vice president")):
        return "leadership"
    if any(term in normalized for term in ("lead", "principal", "staff", "senior")):
        return "senior"
    if any(term in normalized for term in ("junior", "trainee", "intern", "working student")):
        return "early_career"
    return "unspecified"


def _feature_payload(
    *,
    company: Company,
    assessments: list[SignalAssessment],
    cutoff: Any,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    signals = [assessment.signal for assessment in assessments]
    posting_map = {signal.posting_id: signal.posting for signal in signals}
    postings = list(posting_map.values())
    signal_ids = [str(signal.pk) for signal in signals]
    posting_ids = [str(posting.pk) for posting in postings]
    assessment_ids = [str(item.pk) for item in assessments]
    cutoff_30 = cutoff - timedelta(days=30)
    cutoff_90 = cutoff - timedelta(days=90)
    cutoff_180 = cutoff - timedelta(days=180)
    departments = {
        value.casefold()
        for posting in postings
        for value in (posting.department or posting.team,)
        if value and posting.first_seen_at >= cutoff_90
    }
    clusters = {
        cluster.cluster_key
        for assessment in assessments
        for cluster in assessment.capability_clusters.all()
    }
    tag_counts = Counter(tag for signal in signals for tag in signal.capability_tags)
    scores = [item.capability_relevance for item in assessments if item.capability_relevance]
    coverages = [float(item.score_coverage) for item in assessments]
    endpoints = list(company.source_endpoints.all())
    first_party = [
        posting for posting in postings if posting.primary_source_endpoint.company_id == company.pk
    ]
    healthy_endpoints = [
        endpoint
        for endpoint in endpoints
        if endpoint.status == EndpointStatus.ACTIVE and endpoint.last_success_at is not None
    ]
    features: dict[str, Any] = {
        "related_roles_open": sum(
            posting.lifecycle_status == PostingLifecycle.OPEN for posting in postings
        ),
        "related_roles_added_30d": sum(posting.first_seen_at >= cutoff_30 for posting in postings),
        "related_roles_added_90d": sum(posting.first_seen_at >= cutoff_90 for posting in postings),
        "related_roles_closed_90d": sum(
            posting.closed_at is not None and posting.closed_at >= cutoff_90 for posting in postings
        ),
        "roles_reopened_180d": sum(
            signal.signal_type == "role_reopened" and signal.occurred_at >= cutoff_180
            for signal in signals
        ),
        "roles_reposted_180d": sum(
            signal.signal_type == "role_reposted" and signal.occurred_at >= cutoff_180
            for signal in signals
        ),
        "distinct_departments_90d": len(departments),
        "distinct_capability_clusters_90d": len(clusters),
        "seniority_distribution": dict(Counter(_seniority(posting.title) for posting in postings)),
        "employment_type_distribution": dict(
            Counter(posting.employment_type or "unspecified" for posting in postings)
        ),
        "highest_signal_relevance": max(scores) if scores else None,
        "mean_signal_relevance": round(mean(scores), 2) if scores else None,
        "evidence_coverage_mean": round(mean(coverages), 3) if coverages else 0.0,
        "creative_signal_count": tag_counts["creative_ai_production"],
        "learning_signal_count": tag_counts["learning_content"],
        "automation_signal_count": tag_counts["workflow_automation"],
        "infrastructure_signal_count": tag_counts["local_private_ai"]
        + tag_counts["data_integration"],
        "enablement_signal_count": tag_counts["ai_enablement"],
        "first_party_source_ratio": round(len(first_party) / len(postings), 3) if postings else 0.0,
        "signal_recency_days": min(
            ((cutoff - signal.observed_at).days for signal in signals), default=None
        ),
        "source_health": {
            "active_successful": len(healthy_endpoints),
            "total": len(endpoints),
            "status": "healthy" if healthy_endpoints else "unknown_or_degraded",
        },
        "capability_tag_counts": dict(sorted(tag_counts.items())),
    }
    inputs = {
        key: assessment_ids
        if key in {"highest_signal_relevance", "mean_signal_relevance", "evidence_coverage_mean"}
        else posting_ids
        if key
        in {
            "related_roles_open",
            "related_roles_added_30d",
            "related_roles_added_90d",
            "related_roles_closed_90d",
            "distinct_departments_90d",
            "seniority_distribution",
            "employment_type_distribution",
            "first_party_source_ratio",
        }
        else signal_ids
        for key in features
    }
    return features, inputs


def _patterns(features: dict[str, Any]) -> tuple[str, ...]:
    patterns: list[str] = []
    related = int(features["related_roles_added_90d"])
    coverage = float(features["evidence_coverage_mean"])
    if related <= 1:
        patterns.append(PatternKey.ISOLATED_EXPERIMENT)
    if (
        related >= 2
        and int(features["distinct_departments_90d"]) >= 2
        and int(features["distinct_capability_clusters_90d"]) >= 2
        and coverage >= 0.60
    ):
        patterns.append(PatternKey.CROSS_FUNCTIONAL_BUILD)
    if int(features["creative_signal_count"]) >= 2:
        patterns.append(PatternKey.PRODUCTION_EXPANSION)
    if int(features["automation_signal_count"]) + int(features["infrastructure_signal_count"]) >= 2:
        patterns.append(PatternKey.INTERNAL_PLATFORM)
    if int(features["learning_signal_count"]) + int(features["enablement_signal_count"]) >= 1:
        patterns.append(PatternKey.LEARNING_ENABLEMENT)
    tag_counts = cast(dict[str, int], features["capability_tag_counts"])
    if tag_counts.get("local_private_ai", 0) >= 1:
        patterns.append(PatternKey.LOCAL_PRIVATE_AI)
    if related >= 4 and int(features["distinct_capability_clusters_90d"]) >= 3:
        patterns.append(PatternKey.MATURE_INTERNAL_TEAM)
    if not patterns or coverage < 0.40:
        patterns.append(PatternKey.WEAK_AMBIGUOUS)
    return tuple(dict.fromkeys(patterns))


def _company_scores(
    *, company: Company, assessments: list[SignalAssessment], features: dict[str, Any]
) -> tuple[dict[str, ScoreValue], ScoreValue]:
    relevance_scores = [
        Decimal(item.capability_relevance) * item.score_coverage
        for item in assessments
        if item.capability_relevance is not None
    ]
    relevance_weights = [
        item.score_coverage for item in assessments if item.capability_relevance is not None
    ]
    total_relevance_weight = sum(relevance_weights, Decimal("0"))
    capability_score = (
        _rounded(sum(relevance_scores, Decimal("0")) / total_relevance_weight)
        if total_relevance_weight > 0
        else None
    )
    capability_coverage = (
        (total_relevance_weight / Decimal(len(relevance_weights))).quantize(Decimal("0.001"))
        if relevance_weights
        else Decimal("0.000")
    )
    mode_values = [item.opportunity_mode for item in assessments]
    department_count = int(features["distinct_departments_90d"])
    signal_count = len(assessments)
    commercial = _normalized_score(
        {
            "problem_clarity": cast(int | None, features["highest_signal_relevance"]),
            "organizational_commitment": min(100, 40 + 10 * signal_count),
            "vendor_partner_receptivity": None,
            "owner_clarity": min(90, 35 + 15 * department_count),
            "contactability": None,
            "hybrid_delivery_plausibility": 80 if OpportunityMode.HYBRID in mode_values else 30,
            "corroboration": 82 if signal_count >= 2 else 45,
        }
    )
    tag_counts = cast(dict[str, int], features["capability_tag_counts"])
    long_term = _normalized_score(
        {
            "recurring_use_case_potential": min(95, 45 + 10 * signal_count),
            "cross_department_reach": min(95, 30 + 20 * department_count),
            "workflow_volume_scaling_need": 82 if tag_counts.get("workflow_automation", 0) else 45,
            "reproducibility_governance_need": 80
            if tag_counts.get("knowledge_systems", 0) or tag_counts.get("workflow_automation", 0)
            else 40,
            "infrastructure_privacy_need": 85
            if tag_counts.get("local_private_ai", 0)
            else 62
            if tag_counts.get("data_integration", 0)
            else 35,
            "capability_transfer_potential": 82
            if tag_counts.get("learning_content", 0) or tag_counts.get("ai_enablement", 0)
            else 50,
            "continued_partnership_potential": None,
        }
    )
    strategic = ScoreValue(
        company.strategic_fit_manual,
        Decimal("1.000") if company.strategic_fit_manual is not None else Decimal("0.000"),
        () if company.strategic_fit_manual is not None else ("manual_ftl_strategic_fit",),
    )
    scores = {
        "capability_relevance": ScoreValue(
            capability_score,
            capability_coverage,
            () if capability_score is not None else ("completed_signal_assessment",),
        ),
        "commercial_actionability": commercial,
        "long_term_system_potential": long_term,
        "strategic_value": strategic,
    }
    return scores, _priority_score(scores)


def _ambiguous(company: Company) -> bool:
    if company.status == CompanyStatus.MERGE_REVIEW:
        return True
    return CompanyMergeReview.objects.filter(
        Q(left_company=company) | Q(right_company=company), state=MergeReviewState.OPEN
    ).exists()


def _effective_mode(assessments: list[SignalAssessment]) -> str:
    modes = {
        (
            override.opportunity_mode
            if (override := item.overrides.first())
            else item.opportunity_mode
        )
        for item in assessments
    }
    for mode in (
        OpportunityMode.HYBRID,
        OpportunityMode.EXTERNAL_SERVICE,
        OpportunityMode.EMPLOYMENT_ONLY,
        OpportunityMode.WATCH_SIGNAL,
        OpportunityMode.UNKNOWN,
    ):
        if mode in modes:
            return mode
    return OpportunityMode.UNKNOWN


def _qualification(*, priority: int | None, coverage: Decimal, mode: str) -> str:
    if priority is None:
        return QualificationStatus.REVIEW_REQUIRED
    if priority < 40:
        return QualificationStatus.CANDIDATE
    if priority < MIN_RESEARCH_SCORE or coverage < MIN_RESEARCH_COVERAGE:
        return QualificationStatus.WATCHLIST
    if mode not in {OpportunityMode.HYBRID, OpportunityMode.EXTERNAL_SERVICE}:
        return QualificationStatus.WATCHLIST
    return QualificationStatus.RESEARCH_ELIGIBLE


@transaction.atomic
def execute_company_aggregation(envelope: TaskEnvelopeV2) -> bool:
    if envelope.command_type != COMPANIES_AGGREGATE_COMMAND_TYPE:
        raise ValueError("Unsupported company-aggregation command type.")
    run = PipelineRun.objects.select_for_update().get(pk=envelope.pipeline_run_id)
    if run.object_id != envelope.object_id:
        raise ValueError("Envelope object does not match its aggregation run.")
    outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=run)
    if outbox.idempotency_key != envelope.idempotency_key:
        raise ValueError("Envelope idempotency does not match the aggregation command.")
    effect_key = f"{envelope.idempotency_key}:effect"
    if PipelineStepRun.objects.filter(idempotency_key=effect_key).exists():
        return False
    company = Company.objects.select_for_update().get(pk=envelope.object_id)
    cutoff = timezone.now()
    run.status = PipelineStatus.RUNNING
    run.stage = "deterministic_aggregation"
    run.started_at = run.started_at or cutoff
    run.heartbeat_at = cutoff
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
    assessments = list(
        SignalAssessment.objects.filter(
            signal__company=company,
            signal__status=SignalStatus.ACTIVE,
            status=AssessmentStatus.COMPLETED,
            signal__observed_at__lte=cutoff,
        )
        .select_related("signal__posting__primary_source_endpoint")
        .prefetch_related("capability_clusters", "overrides")
        .order_by("signal__observed_at", "pk")
    )
    features, feature_inputs = _feature_payload(
        company=company, assessments=assessments, cutoff=cutoff
    )
    patterns = _patterns(features)
    if assessments:
        scores, priority = _company_scores(
            company=company, assessments=assessments, features=features
        )
    else:
        scores = {
            key: ScoreValue(None, Decimal("0.000"), ("active_signal_assessment",))
            for key in COMPANY_SCORE_WEIGHTS
        }
        priority = ScoreValue(None, Decimal("0.000"), ("active_signal_assessment",))
    selected_signal_ids = [str(item.signal_id) for item in assessments]
    selected_assessment_ids = [str(item.pk) for item in assessments]
    input_payload = {
        "company_id": str(company.pk),
        "cutoff": cutoff.isoformat(),
        "assessment_ids": selected_assessment_ids,
        "assessment_hashes": [item.input_sha256 for item in assessments],
        "feature_builder_version": FEATURE_BUILDER_VERSION,
        "scoring_policy_version": SCORING_POLICY_VERSION,
    }
    ambiguous = _ambiguous(company)
    company_assessment = CompanyAssessment.objects.create(
        company=company,
        pipeline_run=run,
        status=DerivedStatus.REVIEW_REQUIRED if ambiguous else DerivedStatus.COMPLETED,
        feature_cutoff_at=cutoff,
        feature_builder_version=FEATURE_BUILDER_VERSION,
        scoring_policy_version=SCORING_POLICY_VERSION,
        features=features,
        pattern_keys=list(patterns),
        capability_relevance=scores["capability_relevance"].score,
        capability_coverage=scores["capability_relevance"].coverage,
        commercial_actionability=scores["commercial_actionability"].score,
        commercial_coverage=scores["commercial_actionability"].coverage,
        long_term_system_potential=scores["long_term_system_potential"].score,
        long_term_coverage=scores["long_term_system_potential"].coverage,
        strategic_value=scores["strategic_value"].score,
        strategic_coverage=scores["strategic_value"].coverage,
        priority_score=priority.score,
        overall_coverage=priority.coverage,
        selected_signal_ids=selected_signal_ids,
        selected_assessment_ids=selected_assessment_ids,
        missing_components=list(priority.missing),
        input_sha256=_canonical_hash(input_payload),
        idempotency_key=run.idempotency_key,
    )
    for key, value in features.items():
        input_ids = feature_inputs[key]
        CompanyFeature.objects.create(
            company_assessment=company_assessment,
            feature_key=key,
            value=value,
            unit="distribution"
            if isinstance(value, dict)
            else "ratio"
            if isinstance(value, float)
            else "days"
            if key == "signal_recency_days"
            else "count"
            if isinstance(value, int)
            else "score",
            cutoff_at=cutoff,
            input_record_ids=input_ids,
            input_sha256=_canonical_hash({"key": key, "value": value, "inputs": input_ids}),
            feature_builder_version=FEATURE_BUILDER_VERSION,
        )
    for key in patterns:
        CompanyPattern.objects.create(
            company=company,
            company_assessment=company_assessment,
            pattern_key=key,
            feature_cutoff_at=cutoff,
            rule_version=PATTERN_RULE_VERSION,
            input_signal_ids=selected_signal_ids,
            input_sha256=_canonical_hash(
                {"pattern": key, "features": features, "signals": selected_signal_ids}
            ),
            confidence=Decimal("0.900") if key != PatternKey.WEAK_AMBIGUOUS else Decimal("0.650"),
            status=DerivedStatus.COMPLETED,
        )
    opportunity: Opportunity | None = None
    mode = _effective_mode(assessments)
    if not ambiguous and assessments:
        opportunity = (
            Opportunity.objects.select_for_update()
            .filter(company=company, use_case_family=USE_CASE_FAMILY, active=True)
            .first()
        )
        computed_qualification = _qualification(
            priority=priority.score, coverage=priority.coverage, mode=mode
        )
        primary = max(
            assessments,
            key=lambda item: item.capability_relevance or 0,
        ).signal
        if opportunity is None:
            opportunity = Opportunity.objects.create(
                company=company,
                title=f"{company.name} capability systems",
                use_case_family=USE_CASE_FAMILY,
                primary_signal=primary,
                qualification_status=computed_qualification,
                priority_score=priority.score,
                score_coverage=priority.coverage,
                opportunity_mode=mode,
                next_action_key="company_research"
                if computed_qualification == QualificationStatus.RESEARCH_ELIGIBLE
                else "qualification_review",
            )
        else:
            opportunity.primary_signal = primary
            latest_override = opportunity.qualification_overrides.first()
            opportunity.qualification_status = (
                latest_override.selected_status if latest_override else computed_qualification
            )
            opportunity.priority_score = priority.score
            opportunity.score_coverage = priority.coverage
            opportunity.opportunity_mode = mode
            opportunity.next_action_key = (
                "company_research"
                if opportunity.qualification_status == QualificationStatus.RESEARCH_ELIGIBLE
                else "qualification_review"
            )
            opportunity.row_version += 1
            opportunity.save()
        for assessment in assessments:
            OpportunitySignal.objects.get_or_create(
                opportunity=opportunity,
                signal=assessment.signal,
                defaults={
                    "relationship_type": "supporting",
                    "inclusion_reason": "Selected by deterministic company aggregation.",
                },
            )
        company_assessment.opportunity = opportunity
        company_assessment.save(update_fields=("opportunity",))
    elif not assessments:
        stale_opportunities = Opportunity.objects.select_for_update().filter(
            company=company, use_case_family=USE_CASE_FAMILY, active=True
        )
        for stale in stale_opportunities:
            stale.active = False
            stale.next_action_key = "closed_no_active_signals"
            stale.row_version += 1
            stale.save(update_fields=("active", "next_action_key", "row_version", "updated_at"))
    prior_assessments = CompanyAssessment.objects.filter(
        company=company, status=DerivedStatus.COMPLETED
    ).exclude(pk=company_assessment.pk)
    prior_ids = [str(value) for value in prior_assessments.values_list("pk", flat=True)]
    prior_assessments.update(status=DerivedStatus.SUPERSEDED)
    completed = timezone.now()
    PipelineStepRun.objects.create(
        pipeline_run=run,
        stage="company_aggregation",
        status=StepStatus.COMPLETE,
        idempotency_key=effect_key,
        started_at=run.started_at,
        heartbeat_at=completed,
        completed_at=completed,
        input_ids=input_payload,
        output_ids={
            "company_assessment_id": str(company_assessment.pk),
            "opportunity_id": str(opportunity.pk) if opportunity else None,
            "superseded_assessment_ids": prior_ids,
        },
    )
    run.status = PipelineStatus.COMPLETE
    run.stage = "aggregation_complete"
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
        action="companies.aggregation_completed",
        object_type="company_assessment",
        object_id=company_assessment.pk,
        before_summary={},
        after_summary={
            "status": company_assessment.status,
            "priority_score": priority.score,
            "coverage": str(priority.coverage),
            "patterns": list(patterns),
            "opportunity_id": str(opportunity.pk) if opportunity else None,
        },
        reason_key="time_bounded_deterministic_aggregation",
        request_id=run.request_id,
        pipeline_run=run,
    )
    return True


@transaction.atomic
def mark_aggregation_failed(*, pipeline_run_id: UUID, error: Exception) -> None:
    run = PipelineRun.objects.select_for_update().get(pk=pipeline_run_id)
    if run.status == PipelineStatus.COMPLETE:
        return
    message = (str(error).replace("\n", " ").strip() or error.__class__.__name__)[:500]
    code = (
        "AGGREGATION_VALIDATION_FAILED"
        if isinstance(error, AggregationValidationError)
        else "COMPANY_AGGREGATION_FAILED"
    )
    now = timezone.now()
    run.status = PipelineStatus.FAILED
    run.stage = "aggregation_failed"
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
        action="companies.aggregation_failed",
        object_type="company",
        object_id=cast(UUID, run.object_id),
        before_summary={},
        after_summary={"status": PipelineStatus.FAILED, "error_code": code},
        reason_key=code.casefold(),
        request_id=run.request_id,
        pipeline_run=run,
    )


@transaction.atomic
def override_qualification(
    *, opportunity_id: UUID, actor: User, selected_status: str, reason: str, request_id: UUID | None
) -> Opportunity:
    normalized_reason = " ".join(reason.split())[:500]
    if selected_status not in QualificationStatus.values:
        raise AggregationValidationError("Unknown qualification status.")
    if len(normalized_reason) < 5:
        raise AggregationValidationError("Override reason must be at least five characters.")
    opportunity = Opportunity.objects.select_for_update().get(pk=opportunity_id)
    prior = opportunity.qualification_status
    QualificationOverride.objects.create(
        opportunity=opportunity,
        actor=actor,
        prior_status=prior,
        selected_status=selected_status,
        reason=normalized_reason,
    )
    opportunity.qualification_status = selected_status
    opportunity.row_version += 1
    opportunity.save(update_fields=("qualification_status", "row_version", "updated_at"))
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="opportunities.qualification_overridden",
        object_type="opportunity",
        object_id=opportunity.pk,
        before_summary={"qualification_status": prior},
        after_summary={"qualification_status": selected_status},
        reason_key=normalized_reason,
        request_id=request_id,
    )
    return opportunity


def schedule_all_current_companies(*, limit: int = 100) -> int:
    latest = (
        SignalAssessment.objects.filter(
            status=AssessmentStatus.COMPLETED,
            signal__status=SignalStatus.ACTIVE,
        )
        .select_related("signal__company", "pipeline_run")
        .order_by("signal__company_id", "-completed_at")
    )
    scheduled = 0
    seen: set[UUID] = set()
    for assessment in latest:
        if assessment.signal.company_id in seen:
            continue
        seen.add(assessment.signal.company_id)
        result = schedule_company_aggregation(
            assessment.signal.company, trigger_assessment=assessment
        )
        scheduled += int(result.created)
        if scheduled >= limit:
            break
    return scheduled
