from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.knowledge.models import Asset, KnowledgeRelease, OfferModule
from apps.knowledge.services import active_knowledge_release
from apps.operations.commands import ASSET_MATCH_COMMAND_TYPE, SOLUTION_DESIGN_COMMAND_TYPE
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
from apps.opportunities.models import Opportunity, WorkStatus
from apps.research.models import ClaimType, ResearchRun, ResearchRunStatus
from apps.solutions.contracts import (
    AssetMatchOutputV2,
    BuyerRoleRequirementV2,
    EvidenceBoundStatementV2,
    InfrastructureV2,
    SelectedAssetV2,
    SolutionHypothesisV2,
    SolutionPhaseV2,
)
from apps.solutions.models import (
    AssetMatch,
    AssetSelection,
    OpportunitySolutionState,
    SolutionPhase,
    SolutionStateStatus,
    SolutionVersion,
)

SOLUTION_PROMPT_VERSION = "2.1.0"
SOLUTION_SCHEMA_VERSION = "2.1"
SOLUTION_POLICY_VERSION = "deterministic-1.0.0"
ASSET_MATCHER_VERSION = "deterministic-1.0.0"
EXTERNAL_ASSET_MAX_REVIEW_AGE = timedelta(days=365)
ASSET_URL_MAX_CHECK_AGE = timedelta(days=90)
TOKEN_RE = re.compile(r"[a-z0-9_]+")


class SolutionValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ScheduledSolution:
    pipeline_run: PipelineRun
    outbox: TaskOutbox
    created: bool


def _hash_payload(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _safe_message(error: Exception) -> str:
    return (str(error).replace("\n", " ").strip() or error.__class__.__name__)[:500]


def _current_research(opportunity: Opportunity) -> ResearchRun:
    research = (
        ResearchRun.objects.filter(
            opportunity=opportunity,
            is_current=True,
            status=ResearchRunStatus.COMPLETE,
            expires_at__gt=timezone.now(),
        )
        .prefetch_related("claims", "sources")
        .first()
    )
    if research is None:
        raise SolutionValidationError(
            "A current, completed, non-stale research dossier is required."
        )
    if not research.claims.exists():
        raise SolutionValidationError("The current research dossier has no validated claims.")
    return research


def _active_release() -> KnowledgeRelease:
    release = active_knowledge_release()
    if release is None:
        raise SolutionValidationError("No FTL knowledge release is active.")
    if not release.offers.filter(approved=True).exists():
        raise SolutionValidationError("The active knowledge release has no approved offer module.")
    return release


@transaction.atomic
def request_solution_design(
    *, opportunity_id: UUID, actor: User, request_id: UUID | None = None
) -> ScheduledSolution:
    opportunity = (
        Opportunity.objects.select_for_update().select_related("company").get(pk=opportunity_id)
    )
    if not opportunity.active:
        raise SolutionValidationError("A solution can be designed only for an active opportunity.")
    research = _current_research(opportunity)
    release = _active_release()
    fingerprint = {
        "opportunity_id": str(opportunity.pk),
        "research_run_id": str(research.pk),
        "research_output": _hash_payload(research.extraction_output),
        "knowledge_release_id": str(release.pk),
        "knowledge_manifest": release.manifest_sha256,
        "solution_policy": SOLUTION_POLICY_VERSION,
    }
    idempotency_key = f"solutions.design:{opportunity.pk}:{_hash_payload(fingerprint)}"
    pipeline, created = PipelineRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "pipeline_name": "solutions.design",
            "stage": "solution_design_queued",
            "status": PipelineStatus.QUEUED,
            "trigger": PipelineTrigger.MANUAL,
            "requested_by": actor,
            "request_id": request_id,
            "object_type": "opportunity",
            "object_id": opportunity.pk,
            "heartbeat_at": timezone.now(),
            "input_count": research.claims.count(),
            "policy_versions": {
                "solution_prompt": SOLUTION_PROMPT_VERSION,
                "solution_schema": SOLUTION_SCHEMA_VERSION,
                "solution_policy": SOLUTION_POLICY_VERSION,
                "knowledge_release": release.version,
            },
            "context": {
                "research_run_id": str(research.pk),
                "knowledge_release_id": str(release.pk),
            },
        },
    )
    if not created:
        return ScheduledSolution(
            pipeline_run=pipeline,
            outbox=pipeline.outbox_commands.get(idempotency_key=f"{idempotency_key}:design"),
            created=False,
        )
    payload = TargetCommandPayloadV1(pipeline_run_id=pipeline.pk, object_id=opportunity.pk)
    outbox = TaskOutbox(
        command_type=SOLUTION_DESIGN_COMMAND_TYPE,
        payload=payload.model_dump(mode="json"),
        payload_schema_version="1.0",
        idempotency_key=f"{idempotency_key}:design",
        pipeline_run=pipeline,
        request_id=request_id,
        available_at=timezone.now(),
    )
    outbox.full_clean()
    outbox.save()
    opportunity.solution_status = WorkStatus.IN_PROGRESS
    opportunity.next_action_key = "solution_design_in_progress"
    opportunity.row_version += 1
    opportunity.save(
        update_fields=("solution_status", "next_action_key", "row_version", "updated_at")
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="solutions.design_queued",
        object_type="opportunity",
        object_id=opportunity.pk,
        after_summary={
            "research_run_id": str(research.pk),
            "knowledge_release_id": str(release.pk),
        },
        reason_key="current_research_and_knowledge_bound",
        request_id=request_id,
        pipeline_run=pipeline,
    )
    return ScheduledSolution(pipeline_run=pipeline, outbox=outbox, created=True)


def _validate_envelope(
    envelope: TaskEnvelopeV2, command_type: str
) -> tuple[PipelineRun, TaskOutbox]:
    if envelope.command_type != command_type:
        raise SolutionValidationError("Unsupported solution command type.")
    pipeline = PipelineRun.objects.get(pk=envelope.pipeline_run_id)
    outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=pipeline)
    if outbox.idempotency_key != envelope.idempotency_key:
        raise SolutionValidationError("Envelope idempotency does not match the outbox command.")
    return pipeline, outbox


def _patterns(opportunity: Opportunity) -> set[str]:
    assessment = opportunity.company_assessments.order_by("-created_at").first()
    return set(assessment.pattern_keys if assessment else [])


def _signal_tags(opportunity: Opportunity) -> set[str]:
    values: set[str] = set()
    for link in opportunity.signal_links.select_related("signal"):
        values.update(str(tag) for tag in link.signal.capability_tags)
    return values


def _solution_layers(
    *, offer: OfferModule, opportunity: Opportunity, research: ResearchRun
) -> tuple[str, ...]:
    allowed = list(cast(list[str], offer.ftl_layers))
    patterns = _patterns(opportunity)
    tags = _signal_tags(opportunity)
    selected: list[str] = []
    if "create" in allowed:
        selected.append("create")
    if "build" in allowed and (patterns or tags):
        selected.append("build")
    if (
        "deploy" in allowed
        and research.claims.filter(claim_category="infrastructure_privacy_governance").exists()
    ):
        selected.append("deploy")
    if "enable" in allowed and (
        "learning_and_enablement_program" in patterns
        or bool(tags & {"learning_content", "ai_enablement"})
    ):
        selected.append("enable")
    return tuple(selected or allowed[:1])


def _phase_for_layer(
    layer: str, order: int, evidence_refs: tuple[str, ...], offer: OfferModule
) -> SolutionPhaseV2:
    values = {
        "create": (
            "Focused pilot",
            "Validate one bounded, high-value result against the observed capability need.",
            "One reviewable pilot result",
        ),
        "build": (
            "Reusable production system",
            "Turn the validated pilot method into a repeatable and governed workflow.",
            "A documented reusable workflow",
        ),
        "deploy": (
            "Infrastructure discovery gate",
            "Validate environment, privacy, security, and governance constraints before "
            "deployment.",
            "An evidence-backed infrastructure decision record",
        ),
        "enable": (
            "Internal capability transfer",
            "Enable the responsible internal team to operate and improve the capability.",
            "A role-appropriate enablement and handover package",
        ),
    }
    name, objective, deliverable = values[layer]
    configured = cast(list[str], offer.typical_deliverables)
    return SolutionPhaseV2(
        order=order,
        name=name,
        objective=objective,
        deliverables=tuple(configured[:3]) or (deliverable,),
        client_inputs=("Access to the responsible owner and current public/internal constraints.",),
        success_criteria=("The responsible owner can review the output against agreed criteria.",),
        dependencies=() if order == 1 else ("Completion and review of the prior phase.",),
        evidence_refs=evidence_refs,
        assumptions=(),
        optional=layer in {"deploy", "enable"},
    )


def _build_solution(
    *, opportunity: Opportunity, research: ResearchRun, release: KnowledgeRelease
) -> tuple[SolutionHypothesisV2, OfferModule]:
    offer = release.offers.filter(approved=True).order_by("key").first()
    if offer is None:
        raise SolutionValidationError("The active release has no approved offer.")
    claims = list(research.claims.order_by("public_id"))
    lead = next((item for item in claims if item.claim_type == ClaimType.OBSERVED_FACT), claims[0])
    evidence_refs = tuple(item.public_id for item in claims[:8])
    layers = _solution_layers(offer=offer, opportunity=opportunity, research=research)
    phases = tuple(
        _phase_for_layer(layer, order, evidence_refs, offer)
        for order, layer in enumerate(layers, start=1)
    )
    infrastructure_claims = [
        item for item in claims if item.claim_category == "infrastructure_privacy_governance"
    ]
    infrastructure_refs = tuple(item.public_id for item in infrastructure_claims)
    infra_questions = (
        "Which security, privacy, hosting, and governance constraints must a future system meet?",
    )
    prohibited = tuple(
        release.prohibited_claims.order_by("claim_key").values_list("wording", flat=True)
    )
    research_unknowns = tuple(
        str(value)[:500]
        for value in cast(list[object], research.extraction_output.get("unknowns", []))[:20]
    )
    confidence = min(
        Decimal("0.900"), sum((item.confidence for item in claims), Decimal(0)) / len(claims)
    )
    solution = SolutionHypothesisV2(
        schema_version="2.1",
        prompt_version="2.1.0",
        opportunity_name=f"{opportunity.company.name} capability-system hypothesis",
        problem_hypothesis=EvidenceBoundStatementV2(
            statement=(
                "The validated public evidence suggests a capability need that may benefit "
                f"from a bounded pilot and reusable operating method: {lead.statement}"
            ),
            kind="hypothesis",
            confidence=float(confidence),
            evidence_refs=evidence_refs,
        ),
        entry_offer=offer.key,
        ftl_layers=layers,  # type: ignore[arg-type]
        phases=phases,
        infrastructure=InfrastructureV2(
            recommended_mode="unknown",
            rationale=(
                "Infrastructure remains a discovery decision; public evidence does not confirm "
                "the internal environment or data-sensitivity requirements."
            ),
            evidence_refs=infrastructure_refs,
            assumptions=(),
            discovery_questions=infra_questions,
        ),
        long_term_operating_model=(
            "capability_transfer" if "enable" in layers else "managed_capability"
        ),
        immediate_value=(
            "Test one useful result without presenting the inferred company need as confirmed."
        ),
        long_term_value=(
            "If validated, convert the pilot into a governed and repeatable capability rather "
            "than a one-off deliverable."
        ),
        internal_hire_complementarity=(
            "The hypothesis complements the advertised internal capability: FTL can accelerate "
            "a bounded pilot, reusable system, and transfer while internal owners retain authority."
        ),
        buyer_role_requirements=(
            BuyerRoleRequirementV2(
                owner_type="operational_owner",
                responsibility=(
                    "Owns the relevant operating outcome and can validate a bounded pilot."
                ),
            ),
        ),
        asset_match_requirements=tuple(
            f"Demonstrate externally safe evidence relevant to the {layer} layer."
            for layer in layers
        ),
        discovery_questions=(
            "Which operating outcome would make a bounded pilot useful?",
            "Which existing internal work must the engagement complement rather than replace?",
            *infra_questions,
        ),
        risks=(
            "The public hiring signal may represent an internal-only need.",
            "Vendor interest, budget, procurement readiness, and decision authority are unknown.",
        ),
        unknowns=research_unknowns,
        do_not_claim=(
            *prohibited,
            "Do not claim confirmed budget, timeline, procurement readiness, or outcomes.",
        ),
        confidence=float(confidence),
    )
    _validate_solution(solution, opportunity=opportunity, research=research, release=release)
    return solution, offer


def _validate_solution(
    solution: SolutionHypothesisV2,
    *,
    opportunity: Opportunity,
    research: ResearchRun,
    release: KnowledgeRelease,
) -> OfferModule:
    offer = release.offers.filter(key=solution.entry_offer, approved=True).first()
    if offer is None:
        raise SolutionValidationError("The solution references an inactive offer key.")
    orders = [phase.order for phase in solution.phases]
    if orders != list(range(1, len(orders) + 1)):
        raise SolutionValidationError("Solution phases must be uniquely sequential.")
    allowed_refs = set(research.claims.values_list("public_id", flat=True))
    allowed_refs.update(
        str(value) for value in opportunity.signal_links.values_list("signal_id", flat=True)
    )
    for link in opportunity.signal_links.prefetch_related("signal__evidence_links__evidence_item"):
        allowed_refs.update(
            evidence.evidence_item.public_id for evidence in link.signal.evidence_links.all()
        )
    refs = set(solution.problem_hypothesis.evidence_refs)
    for phase in solution.phases:
        refs.update(phase.evidence_refs)
    refs.update(solution.infrastructure.evidence_refs)
    if not refs.issubset(allowed_refs):
        raise SolutionValidationError("The solution references evidence outside its exact input.")
    if "deploy" in solution.ftl_layers and not (
        solution.infrastructure.evidence_refs
        or solution.infrastructure.discovery_questions
        or solution.infrastructure.assumptions
    ):
        raise SolutionValidationError("Deploy requires evidence or an explicit discovery gate.")
    if solution.entry_offer not in {offer.key}:
        raise SolutionValidationError("The entry offer is not active.")
    return cast(OfferModule, offer)


def _create_solution_version(
    *,
    opportunity: Opportunity,
    research: ResearchRun,
    release: KnowledgeRelease,
    offer: OfferModule,
    output: SolutionHypothesisV2,
    pipeline: PipelineRun | None,
    actor: User | None,
    method: str,
) -> SolutionVersion:
    version = (
        SolutionVersion.objects.filter(opportunity=opportunity).aggregate(value=Max("version"))[
            "value"
        ]
        or 0
    ) + 1
    payload = output.model_dump(mode="json")
    input_payload = {
        "opportunity_id": str(opportunity.pk),
        "research_run_id": str(research.pk),
        "research_output_sha256": _hash_payload(research.extraction_output),
        "knowledge_release_id": str(release.pk),
        "knowledge_manifest_sha256": release.manifest_sha256,
    }
    solution_version = SolutionVersion.objects.create(
        opportunity=opportunity,
        research_run=research,
        knowledge_release=release,
        entry_offer=offer,
        pipeline_run=pipeline,
        version=version,
        structured_output=payload,
        output_sha256=_hash_payload(payload),
        input_sha256=_hash_payload(input_payload),
        prompt_version=SOLUTION_PROMPT_VERSION,
        schema_version=SOLUTION_SCHEMA_VERSION,
        generator_method=method,
        created_by=actor,
    )
    SolutionPhase.objects.bulk_create(
        [
            SolutionPhase(
                solution_version=solution_version,
                phase_order=phase.order,
                name=phase.name,
                objective=phase.objective,
                payload=phase.model_dump(mode="json"),
            )
            for phase in output.phases
        ]
    )
    state, _created = OpportunitySolutionState.objects.select_for_update().get_or_create(
        opportunity=opportunity
    )
    state.current_version = solution_version
    state.status = SolutionStateStatus.DRAFT
    state.stale_reason = ""
    state.row_version += 1
    state.save(
        update_fields=(
            "current_version",
            "status",
            "stale_reason",
            "row_version",
            "updated_at",
        )
    )
    return solution_version


def _queue_asset_match(
    *, solution_version: SolutionVersion, pipeline: PipelineRun, request_id: UUID | None
) -> TaskOutbox:
    key = f"solutions.match:{solution_version.pk}:{solution_version.output_sha256}"
    payload = TargetCommandPayloadV1(pipeline_run_id=pipeline.pk, object_id=solution_version.pk)
    outbox = TaskOutbox(
        command_type=ASSET_MATCH_COMMAND_TYPE,
        payload=payload.model_dump(mode="json"),
        payload_schema_version="1.0",
        idempotency_key=key,
        pipeline_run=pipeline,
        request_id=request_id,
        available_at=timezone.now(),
    )
    outbox.full_clean()
    outbox.save()
    return outbox


@transaction.atomic
def execute_solution_design(envelope: TaskEnvelopeV2) -> bool:
    pipeline, _outbox = _validate_envelope(envelope, SOLUTION_DESIGN_COMMAND_TYPE)
    if envelope.object_id != pipeline.object_id:
        raise SolutionValidationError("The solution object does not match its pipeline.")
    effect_key = f"{envelope.idempotency_key}:effect"
    if PipelineStepRun.objects.filter(idempotency_key=effect_key).exists():
        return False
    opportunity = (
        Opportunity.objects.select_for_update().select_related("company").get(pk=envelope.object_id)
    )
    research = _current_research(opportunity)
    release = _active_release()
    expected_release_id = pipeline.context.get("knowledge_release_id")
    expected_research_id = pipeline.context.get("research_run_id")
    if str(release.pk) != expected_release_id or str(research.pk) != expected_research_id:
        raise SolutionValidationError("Research or active knowledge changed before execution.")
    now = timezone.now()
    pipeline.status = PipelineStatus.RUNNING
    pipeline.stage = "solution_design_running"
    pipeline.started_at = pipeline.started_at or now
    pipeline.heartbeat_at = now
    pipeline.attempts += 1
    pipeline.row_version += 1
    pipeline.save()
    output, offer = _build_solution(opportunity=opportunity, research=research, release=release)
    version = _create_solution_version(
        opportunity=opportunity,
        research=research,
        release=release,
        offer=offer,
        output=output,
        pipeline=pipeline,
        actor=pipeline.requested_by,
        method="deterministic",
    )
    completed = timezone.now()
    PipelineStepRun.objects.create(
        pipeline_run=pipeline,
        stage="solution_design",
        status=StepStatus.COMPLETE,
        idempotency_key=effect_key,
        started_at=now,
        heartbeat_at=completed,
        completed_at=completed,
        input_ids={
            "research_run_id": str(research.pk),
            "knowledge_release_id": str(release.pk),
        },
        output_ids={"solution_version_id": str(version.pk)},
    )
    _queue_asset_match(solution_version=version, pipeline=pipeline, request_id=pipeline.request_id)
    pipeline.stage = "asset_matching_queued"
    pipeline.heartbeat_at = completed
    pipeline.output_count = 1
    pipeline.row_version += 1
    pipeline.save(
        update_fields=(
            "stage",
            "heartbeat_at",
            "output_count",
            "row_version",
            "updated_at",
        )
    )
    opportunity.solution_status = WorkStatus.REVIEW
    opportunity.next_action_key = "asset_matching"
    opportunity.row_version += 1
    opportunity.save(
        update_fields=("solution_status", "next_action_key", "row_version", "updated_at")
    )
    AuditEvent.objects.create(
        actor_type=ActorType.SYSTEM,
        action="solutions.version_created",
        object_type="solution_version",
        object_id=version.pk,
        after_summary={
            "version": version.version,
            "output_sha256": version.output_sha256,
            "layers": list(output.ftl_layers),
            "phase_count": len(output.phases),
        },
        reason_key="deterministic_evidence_bound_design",
        request_id=pipeline.request_id,
        pipeline_run=pipeline,
    )
    return True


def _asset_eligibility(asset: Asset, *, now: datetime) -> tuple[bool, str]:
    current = now
    if asset.confidentiality != "public":
        return False, "confidentiality"
    if not asset.approved_for_external_use:
        return False, "not_approved_for_external_use"
    if asset.status != "live":
        return False, "not_live"
    if not set(cast(list[str], asset.languages)) & {"en", "de"}:
        return False, "language"
    if "public_business" not in cast(list[str], asset.audiences):
        return False, "audience"
    if asset.last_reviewed_at < current - EXTERNAL_ASSET_MAX_REVIEW_AGE:
        return False, "review_stale"
    if (
        asset.url_last_checked_at is None
        or asset.url_last_checked_at < current - ASSET_URL_MAX_CHECK_AGE
    ):
        return False, "url_health_stale"
    return True, "eligible"


def _tokens(values: list[str]) -> set[str]:
    return {
        token
        for value in values
        for token in TOKEN_RE.findall(value.casefold().replace("-", "_"))
        if len(token) > 2
    }


@transaction.atomic
def execute_asset_matching(envelope: TaskEnvelopeV2) -> bool:
    pipeline, _outbox = _validate_envelope(envelope, ASSET_MATCH_COMMAND_TYPE)
    effect_key = f"{envelope.idempotency_key}:effect"
    if PipelineStepRun.objects.filter(idempotency_key=effect_key).exists():
        return False
    solution = (
        SolutionVersion.objects.select_related(
            "opportunity", "knowledge_release", "opportunity__solution_state"
        )
        .prefetch_related("phases")
        .get(pk=envelope.object_id)
    )
    if solution.pipeline_run_id != pipeline.pk:
        raise SolutionValidationError("The solution version does not match its pipeline.")
    output = SolutionHypothesisV2.model_validate_json(json.dumps(solution.structured_output))
    now = timezone.now()
    excluded: dict[str, str] = {}
    eligible: list[Asset] = []
    for asset in solution.knowledge_release.assets.order_by("asset_id"):
        allowed, reason = _asset_eligibility(asset, now=now)
        if allowed:
            eligible.append(asset)
        else:
            excluded[asset.asset_id] = reason
    requirement_tokens = _tokens(list(output.asset_match_requirements))
    layers = set(output.ftl_layers)
    ranked: list[tuple[int, str, Asset]] = []
    for asset in eligible:
        asset_tokens = _tokens(
            [
                asset.title,
                asset.short_description,
                asset.detailed_description,
                *cast(list[str], asset.capability_tags),
            ]
        )
        score = len(requirement_tokens & asset_tokens) + 3 * len(
            layers & set(cast(list[str], asset.ftl_layers))
        )
        if score <= 0:
            excluded[asset.asset_id] = "no_material_relevance"
            continue
        ranked.append((score, asset.asset_id, asset))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected: list[SelectedAssetV2] = []
    for priority, (_score, _asset_id, asset) in enumerate(ranked[:2], start=1):
        supported_phase = next(
            (
                phase.order
                for phase in output.phases
                if set(cast(list[str], asset.ftl_layers)) & layers
            ),
            1,
        )
        selected.append(
            SelectedAssetV2(
                asset_id=asset.asset_id,
                relevance_reason=(
                    "This active public asset overlaps the solution layers and the explicit "
                    "asset-match requirements."
                ),
                priority=priority,
                supported_solution_phase=supported_phase,
            )
        )
    selected_ids = {item.asset_id for item in selected}
    for _score, asset_id, _asset in ranked[2:]:
        excluded[asset_id] = "maximum_two_assets"
    match_output = AssetMatchOutputV2(
        schema_version="2.1",
        prompt_version="2.1.0",
        solution_id=solution.pk,
        selected_assets=tuple(selected),
        excluded_asset_ids=tuple(sorted(excluded)),
        unknowns=(
            ()
            if selected
            else ("No current externally safe asset materially matched this solution.",)
        ),
        review_flags=(),
    )
    payload = match_output.model_dump(mode="json")
    match = AssetMatch.objects.create(
        solution_version=solution,
        knowledge_release=solution.knowledge_release,
        pipeline_run=pipeline,
        output_payload=payload,
        output_sha256=_hash_payload(payload),
        matcher_version=ASSET_MATCHER_VERSION,
        candidate_asset_ids=[asset.asset_id for asset in eligible],
        excluded_reasons=excluded,
    )
    asset_map = {
        asset.asset_id: asset
        for asset in solution.knowledge_release.assets.filter(asset_id__in=selected_ids)
    }
    AssetSelection.objects.bulk_create(
        [
            AssetSelection(
                asset_match=match,
                asset=asset_map[item.asset_id],
                priority=item.priority,
                supported_solution_phase=item.supported_solution_phase,
                relevance_reason=item.relevance_reason,
            )
            for item in selected
        ]
    )
    completed = timezone.now()
    PipelineStepRun.objects.create(
        pipeline_run=pipeline,
        stage="asset_matching",
        status=StepStatus.COMPLETE,
        idempotency_key=effect_key,
        started_at=completed,
        heartbeat_at=completed,
        completed_at=completed,
        input_ids={
            "solution_version_id": str(solution.pk),
            "knowledge_release_id": str(solution.knowledge_release_id),
        },
        output_ids={
            "asset_match_id": str(match.pk),
            "selected_asset_ids": [item.asset_id for item in selected],
        },
    )
    pipeline.status = PipelineStatus.COMPLETE
    pipeline.stage = "solution_and_asset_match_complete"
    pipeline.completed_at = completed
    pipeline.heartbeat_at = completed
    pipeline.output_count = 1 + len(selected)
    pipeline.row_version += 1
    pipeline.save(
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
    opportunity = solution.opportunity
    opportunity.solution_status = WorkStatus.REVIEW
    opportunity.next_action_key = "review_solution"
    opportunity.row_version += 1
    opportunity.save(
        update_fields=("solution_status", "next_action_key", "row_version", "updated_at")
    )
    AuditEvent.objects.create(
        actor_type=ActorType.SYSTEM,
        action="solutions.assets_matched",
        object_type="asset_match",
        object_id=match.pk,
        after_summary={
            "selected_asset_ids": [item.asset_id for item in selected],
            "zero_asset_result": not selected,
            "output_sha256": match.output_sha256,
        },
        reason_key="python_filtered_deterministic_matching",
        request_id=pipeline.request_id,
        pipeline_run=pipeline,
    )
    return True


@transaction.atomic
def create_edited_solution(
    *, solution_id: UUID, actor: User, payload_json: str, request_id: UUID | None
) -> ScheduledSolution:
    source = SolutionVersion.objects.select_related(
        "opportunity", "research_run", "knowledge_release", "entry_offer"
    ).get(pk=solution_id)
    state = OpportunitySolutionState.objects.select_for_update().get(opportunity=source.opportunity)
    if state.current_version_id != source.pk:
        raise SolutionValidationError("Only the current solution version can be edited.")
    try:
        output = SolutionHypothesisV2.model_validate_json(payload_json)
    except Exception as exc:
        raise SolutionValidationError("The edited solution failed its strict schema.") from exc
    offer = _validate_solution(
        output,
        opportunity=source.opportunity,
        research=source.research_run,
        release=source.knowledge_release,
    )
    input_hash = _hash_payload(
        {
            "source_solution_id": str(source.pk),
            "edited_output": output.model_dump(mode="json"),
        }
    )
    pipeline = PipelineRun.objects.create(
        pipeline_name="solutions.asset_rematch",
        stage="asset_matching_queued",
        status=PipelineStatus.RUNNING,
        trigger=PipelineTrigger.MANUAL,
        requested_by=actor,
        request_id=request_id,
        idempotency_key=f"solutions.edit:{source.opportunity_id}:{input_hash}",
        object_type="opportunity",
        object_id=source.opportunity_id,
        started_at=timezone.now(),
        heartbeat_at=timezone.now(),
        input_count=1,
        policy_versions={
            "solution_prompt": SOLUTION_PROMPT_VERSION,
            "asset_matcher": ASSET_MATCHER_VERSION,
        },
        context={"source_solution_id": str(source.pk)},
    )
    version = _create_solution_version(
        opportunity=source.opportunity,
        research=source.research_run,
        release=source.knowledge_release,
        offer=offer,
        output=output,
        pipeline=pipeline,
        actor=actor,
        method="human_edit",
    )
    outbox = _queue_asset_match(solution_version=version, pipeline=pipeline, request_id=request_id)
    source.opportunity.solution_status = WorkStatus.REVIEW
    source.opportunity.next_action_key = "asset_matching"
    source.opportunity.row_version += 1
    source.opportunity.save(
        update_fields=("solution_status", "next_action_key", "row_version", "updated_at")
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="solutions.version_edited",
        object_type="solution_version",
        object_id=version.pk,
        before_summary={"source_version_id": str(source.pk)},
        after_summary={"version": version.version, "output_sha256": version.output_sha256},
        reason_key="human_structured_edit",
        request_id=request_id,
        pipeline_run=pipeline,
    )
    return ScheduledSolution(pipeline_run=pipeline, outbox=outbox, created=True)


@transaction.atomic
def approve_solution(
    *, solution_id: UUID, actor: User, reason: str, request_id: UUID | None
) -> OpportunitySolutionState:
    normalized_reason = " ".join(reason.split())[:500]
    if len(normalized_reason) < 5:
        raise SolutionValidationError("Approval reason must be at least five characters.")
    solution = SolutionVersion.objects.select_related("opportunity").get(pk=solution_id)
    state = OpportunitySolutionState.objects.select_for_update().get(
        opportunity=solution.opportunity
    )
    if state.current_version_id != solution.pk:
        raise SolutionValidationError("Only the current solution version can be approved.")
    if not hasattr(solution, "asset_match"):
        raise SolutionValidationError("Asset matching must finish before solution approval.")
    before = {
        "status": state.status,
        "approved_version_id": str(state.approved_version_id or ""),
    }
    state.approved_version = solution
    state.status = SolutionStateStatus.APPROVED
    state.approved_by = actor
    state.approved_at = timezone.now()
    state.stale_reason = ""
    state.row_version += 1
    state.save()
    opportunity = solution.opportunity
    opportunity.solution_status = WorkStatus.COMPLETE
    opportunity.next_action_key = "buyer_role_research"
    opportunity.row_version += 1
    opportunity.save(
        update_fields=("solution_status", "next_action_key", "row_version", "updated_at")
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="solutions.version_approved",
        object_type="solution_version",
        object_id=solution.pk,
        before_summary=before,
        after_summary={
            "status": state.status,
            "approved_version_id": str(solution.pk),
            "output_sha256": solution.output_sha256,
            "asset_match_sha256": solution.asset_match.output_sha256,
        },
        reason_key=normalized_reason,
        request_id=request_id,
    )
    return state


@transaction.atomic
def invalidate_for_knowledge_release(*, active_release_id: UUID) -> int:
    states = (
        OpportunitySolutionState.objects.select_for_update()
        .select_related("current_version", "opportunity")
        .exclude(current_version__isnull=True)
    )
    invalidated = 0
    for state in states:
        if (
            state.current_version is None
            or state.current_version.knowledge_release_id == active_release_id
        ):
            continue
        state.status = SolutionStateStatus.STALE
        state.stale_reason = "The active FTL knowledge release changed."
        state.row_version += 1
        state.save(update_fields=("status", "stale_reason", "row_version", "updated_at"))
        opportunity = state.opportunity
        opportunity.solution_status = WorkStatus.REVIEW
        opportunity.next_action_key = "refresh_solution_for_knowledge_release"
        opportunity.row_version += 1
        opportunity.save(
            update_fields=("solution_status", "next_action_key", "row_version", "updated_at")
        )
        AuditEvent.objects.create(
            actor_type=ActorType.SYSTEM,
            action="solutions.version_stale",
            object_type="solution_version",
            object_id=state.current_version.pk,
            after_summary={"active_knowledge_release_id": str(active_release_id)},
            reason_key="knowledge_release_changed",
        )
        invalidated += 1
    return invalidated


@transaction.atomic
def mark_solution_failed(*, pipeline_run_id: UUID, error: Exception) -> None:
    pipeline = PipelineRun.objects.select_for_update().get(pk=pipeline_run_id)
    if pipeline.status == PipelineStatus.COMPLETE:
        return
    now = timezone.now()
    message = _safe_message(error)
    pipeline.status = PipelineStatus.FAILED
    pipeline.stage = "solution_pipeline_failed"
    pipeline.completed_at = now
    pipeline.heartbeat_at = now
    pipeline.error_count += 1
    pipeline.last_error_code = "SOLUTION_VALIDATION_FAILED"
    pipeline.last_error_message = message
    pipeline.row_version += 1
    pipeline.save()
    if pipeline.object_id is not None:
        opportunity = Opportunity.objects.filter(pk=pipeline.object_id).first()
        if opportunity is not None:
            opportunity.solution_status = WorkStatus.REVIEW
            opportunity.next_action_key = "review_solution_failure"
            opportunity.row_version += 1
            opportunity.save(
                update_fields=(
                    "solution_status",
                    "next_action_key",
                    "row_version",
                    "updated_at",
                )
            )
    AuditEvent.objects.create(
        actor_type=ActorType.SYSTEM,
        action="solutions.pipeline_failed",
        object_type="pipeline_run",
        object_id=pipeline.pk,
        after_summary={"error_code": pipeline.last_error_code},
        reason_key="solution_validation_failed",
        request_id=pipeline.request_id,
        pipeline_run=pipeline,
    )
