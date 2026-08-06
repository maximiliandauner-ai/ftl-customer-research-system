from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal, cast
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.operations.commands import (
    RESEARCH_EXTRACT_COMMAND_TYPE,
    RESEARCH_PUBLIC_COMMAND_TYPE,
)
from apps.operations.contracts import TargetCommandPayloadV1, TaskEnvelopeV2
from apps.operations.models import (
    ActorType,
    AuditEvent,
    PipelineRun,
    PipelineStatus,
    PipelineStepRun,
    PipelineTrigger,
    ProviderCall,
    StepStatus,
    TaskOutbox,
)
from apps.opportunities.models import Opportunity, QualificationStatus, ResearchStatus
from apps.providers.contracts import ProviderSourceV1
from apps.providers.openai import (
    OpenAIResponsesProvider,
    ProviderBudgetBlocked,
    ProviderError,
    ProviderIncomplete,
    ProviderRefused,
    ProviderSchemaInvalid,
    StandardResearchProvider,
)
from apps.providers.policy import active_model_policy
from apps.research.contracts import (
    BriefFactV2,
    PublicCompanyContextV2,
    RegisteredSourceV2,
    ResearchBriefV2,
    ResearchExtractionRequestV2,
    ResearchExtractionV2,
    ResearchSourcePolicyV2,
    WebResearchRequestV2,
)
from apps.research.models import (
    ClaimType,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchClaimSignal,
    ResearchClaimSource,
    ResearchDossier,
    ResearchReportArtifact,
    ResearchRun,
    ResearchRunStatus,
    ResearchSource,
    ResearchSourceType,
)
from apps.signals.models import SignalEvent, SignalStatus
from apps.sources.policy import SourcePolicyError, canonicalize_url, registrable_domain

PUBLIC_POLICY_KEY = "research.standard_web"
EXTRACTION_POLICY_KEY = "research.standard_extract"
BRIEF_PROMPT_VERSION: Literal["2.1.0"] = "2.1.0"
RESEARCH_PROMPT_VERSION = "2.1.0"
EXTRACTION_PROMPT_VERSION = "2.1.0"
SCHEMA_VERSION = "2.1"
DOSSIER_RENDERER_VERSION = "1.0.0"
REPORT_MAX_BYTES = 100_000
STALE_AFTER_DAYS = 30

REQUIRED_REPORT_HEADINGS = (
    "Executive Summary",
    "Company and Business Context",
    "Observed Capability Signal",
    "Relevant Current Initiatives",
    "Organizational Ownership Context",
    "External-Partner and Procurement Signals",
    "Infrastructure, Privacy, and Governance Context",
    "Evidence Against the Opportunity",
    "Material Unknowns",
    "Source Notes",
)
PROHIBITED_CLAIM_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b(final buyer|decision[- ]maker|warm introduction)\b", re.IGNORECASE),
    re.compile(r"\b(FTL should|recommended solution|send (?:an )?email)\b", re.IGNORECASE),
)


class ResearchRequestError(ValueError):
    pass


class ResearchValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ScheduledResearch:
    research_run: ResearchRun
    outbox: TaskOutbox
    created: bool


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_payload(value: object) -> str:
    return _sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )


def _safe_message(error: Exception) -> str:
    return (str(error).replace("\n", " ").strip() or error.__class__.__name__)[:500]


def _active_signals(opportunity: Opportunity) -> list[SignalEvent]:
    return list(
        SignalEvent.objects.filter(
            opportunity_links__opportunity=opportunity,
            status=SignalStatus.ACTIVE,
        )
        .select_related("posting", "posting__primary_source_endpoint")
        .prefetch_related("evidence_links__evidence_item")
        .distinct()
        .order_by("observed_at", "pk")
    )


def _official_urls(opportunity: Opportunity, signals: list[SignalEvent]) -> tuple[str, ...]:
    values: set[str] = set()
    for domain in opportunity.company.domains.exclude(verification_status="disputed").order_by(
        "-is_primary", "hostname_ascii"
    ):
        values.add(f"https://{domain.hostname_ascii}/")
        if domain.verification_source_url:
            values.add(domain.verification_source_url)
    for signal in signals:
        values.add(signal.posting.canonical_url)
        values.add(signal.posting.source_url)
        values.add(signal.posting.primary_source_endpoint.base_url_canonical)
    return tuple(sorted(value for value in values if value))[:30]


def _build_brief(
    opportunity: Opportunity, signals: list[SignalEvent]
) -> tuple[ResearchBriefV2, WebResearchRequestV2]:
    facts: list[BriefFactV2] = []
    for ordinal, signal in enumerate(signals, start=1):
        evidence_ids = tuple(link.evidence_item.public_id for link in signal.evidence_links.all())
        if not evidence_ids:
            raise ResearchRequestError("Every selected signal must have immutable evidence.")
        tags = ", ".join(str(value) for value in signal.capability_tags[:12])
        statement = (
            f"Public job signal '{signal.posting.title}' was observed as "
            f"{signal.signal_type}; capability tags: {tags or 'none recorded'}. "
            f"Recorded rationale: {signal.rationale}"
        )[:2_000]
        facts.append(
            BriefFactV2(
                fact_id=f"FACT-{ordinal:06d}",
                statement=statement,
                signal_id=signal.pk,
                evidence_ids=evidence_ids,
            )
        )
    primary_domain = (
        opportunity.company.domains.filter(is_primary=True)
        .values_list("hostname_ascii", flat=True)
        .first()
        or ""
    )
    if not primary_domain:
        primary_domain = registrable_domain(
            urlsplit(signal.posting.primary_source_endpoint.base_url_canonical).hostname or ""
            if (signal := signals[0])
            else ""
        )
    official_urls = _official_urls(opportunity, signals)
    brief = ResearchBriefV2(
        schema_version="2.1",
        prompt_version=BRIEF_PROMPT_VERSION,
        objective=(
            "Establish current public company context for the observed capability demand, "
            "including corroboration, ownership context, partner signals, constraints, and "
            "evidence that weakens the opportunity."
        ),
        company_identity_note=(
            f"Research the public organization named {opportunity.company.name!r} associated "
            f"with the verified or observed domain {primary_domain!r}; flag identity ambiguity."
        ),
        known_observed_facts=tuple(facts),
        questions=(
            "What does the company publicly state about its business, scale, and "
            "current priorities?",
            "Which current initiatives corroborate the observed capability demand?",
            "Which functions publicly appear to own the relevant work, without selecting buyers?",
            "Is there evidence of external-partner or procurement openness?",
            "Which infrastructure, privacy, security, or governance constraints are public?",
        ),
        disconfirming_questions=(
            "What evidence suggests the need is already fully covered internally?",
            "What evidence suggests the observed jobs are isolated or no longer current?",
        ),
        required_fact_categories=(
            "company_profile",
            "signal_context",
            "current_initiatives",
            "organizational_ownership",
            "external_partner_context",
            "infrastructure_privacy_governance",
            "evidence_against",
        ),
        source_policy=ResearchSourcePolicyV2(
            prefer_first_party=True,
            allowed_domains=(primary_domain,) if primary_domain else (),
            blocked_domains=("linkedin.com", "facebook.com", "xing.com"),
            maximum_tool_calls=18,
            maximum_sources=40,
            freshness_window_days=365,
        ),
        explicit_exclusions=(
            "Do not identify final buyer roles or named contact people.",
            "Do not infer email addresses or use gated/private networks.",
            "Do not select FTL assets, offers, or solutions and do not draft outreach.",
            "Do not include private FTL knowledge or CRM context.",
        ),
        unknowns_to_resolve=(
            "Whether the public signal reflects a durable cross-functional initiative.",
            "Whether external support is plausible or the work is explicitly internal-only.",
        ),
        stop_conditions=(
            "Stop when source or tool bounds are reached.",
            "Preserve material unknowns rather than filling gaps with assumptions.",
        ),
        review_flags=(),
    )
    request = WebResearchRequestV2(
        schema_version="2.1",
        company=PublicCompanyContextV2(
            company_id=opportunity.company_id,
            name=opportunity.company.name,
            primary_domain=primary_domain,
            known_official_urls=official_urls,
        ),
        brief=brief,
        max_tool_calls=18,
        max_sources=40,
        max_provider_cost_usd=1.5,
    )
    return brief, request


def _require_research_configuration() -> None:
    features = settings.RUNTIME_SETTINGS.features
    if not (
        features.openai_enabled
        and features.web_search_enabled
        and features.standard_research_enabled
    ):
        raise ResearchRequestError(
            "Standard research is disabled. Enable OPENAI_ENABLED, WEB_SEARCH_ENABLED, "
            "and STANDARD_RESEARCH_ENABLED with an approved API key and budget."
        )


@transaction.atomic
def request_standard_research(
    *, opportunity_id: UUID, actor: User, request_id: UUID | None = None
) -> ScheduledResearch:
    _require_research_configuration()
    opportunity = (
        Opportunity.objects.select_for_update().select_related("company").get(pk=opportunity_id)
    )
    if not opportunity.active:
        raise ResearchRequestError("Research can be requested only for an active opportunity.")
    if opportunity.qualification_status not in {
        QualificationStatus.RESEARCH_ELIGIBLE,
        QualificationStatus.QUALIFIED,
    }:
        raise ResearchRequestError("The opportunity is not currently research eligible.")
    public_policy = active_model_policy(PUBLIC_POLICY_KEY)
    extraction_policy = active_model_policy(EXTRACTION_POLICY_KEY)
    signals = _active_signals(opportunity)
    if not signals:
        raise ResearchRequestError("The opportunity has no active supporting signals.")
    brief, public_request = _build_brief(opportunity, signals)
    company_assessment = opportunity.company_assessments.order_by("-created_at").first()
    input_fingerprint = {
        "opportunity_id": str(opportunity.pk),
        "company_assessment_id": str(company_assessment.pk) if company_assessment else "",
        "company_assessment_input": (company_assessment.input_sha256 if company_assessment else ""),
        "signals": [str(signal.pk) for signal in signals],
        "signal_inputs": [signal.idempotency_key for signal in signals],
        "public_policy": public_policy.policy_sha256,
        "extraction_policy": extraction_policy.policy_sha256,
    }
    idempotency_key = f"research.standard:{opportunity.pk}:{_sha256_payload(input_fingerprint)}"
    existing = ResearchRun.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return ScheduledResearch(
            research_run=existing,
            outbox=existing.pipeline_run.outbox_commands.get(
                idempotency_key=f"{idempotency_key}:public"
            ),
            created=False,
        )
    now = timezone.now()
    pipeline = PipelineRun.objects.create(
        pipeline_name="research.standard",
        stage="public_research_queued",
        status=PipelineStatus.QUEUED,
        trigger=PipelineTrigger.MANUAL,
        requested_by=actor,
        request_id=request_id,
        idempotency_key=idempotency_key,
        object_type="research_run",
        heartbeat_at=now,
        input_count=len(signals),
        policy_versions={
            PUBLIC_POLICY_KEY: public_policy.version,
            EXTRACTION_POLICY_KEY: extraction_policy.version,
            "research_brief": BRIEF_PROMPT_VERSION,
            "company_researcher": RESEARCH_PROMPT_VERSION,
            "research_extractor": EXTRACTION_PROMPT_VERSION,
            "schema": SCHEMA_VERSION,
        },
        context={"opportunity_id": str(opportunity.pk)},
    )
    ResearchRun.objects.filter(opportunity=opportunity, is_current=True).update(is_current=False)
    version = (
        ResearchRun.objects.filter(opportunity=opportunity).aggregate(value=Max("version"))["value"]
        or 0
    ) + 1
    brief_payload = brief.model_dump(mode="json")
    public_payload = public_request.model_dump(mode="json")
    research_run = ResearchRun.objects.create(
        opportunity=opportunity,
        pipeline_run=pipeline,
        requested_by=actor,
        version=version,
        status=ResearchRunStatus.QUEUED,
        brief_payload=brief_payload,
        brief_sha256=_sha256_payload(brief_payload),
        public_input_payload=public_payload,
        public_input_sha256=_sha256_payload(public_payload),
        research_prompt_version=RESEARCH_PROMPT_VERSION,
        extraction_prompt_version=EXTRACTION_PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        public_policy_key=public_policy.policy_key,
        public_policy_version=public_policy.version,
        extraction_policy_key=extraction_policy.policy_key,
        extraction_policy_version=extraction_policy.version,
        idempotency_key=idempotency_key,
    )
    pipeline.object_id = research_run.pk
    pipeline.save(update_fields=("object_id", "updated_at"))
    payload = TargetCommandPayloadV1(pipeline_run_id=pipeline.pk, object_id=research_run.pk)
    outbox = TaskOutbox(
        command_type=RESEARCH_PUBLIC_COMMAND_TYPE,
        payload=payload.model_dump(mode="json"),
        payload_schema_version="1.0",
        idempotency_key=f"{idempotency_key}:public",
        pipeline_run=pipeline,
        request_id=request_id,
        available_at=now,
    )
    outbox.full_clean()
    outbox.save()
    opportunity.research_status = ResearchStatus.QUEUED
    opportunity.next_action_key = "research_in_progress"
    opportunity.row_version += 1
    opportunity.save(
        update_fields=(
            "research_status",
            "next_action_key",
            "row_version",
            "updated_at",
        )
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="research.standard_queued",
        object_type="research_run",
        object_id=research_run.pk,
        after_summary={
            "status": research_run.status,
            "opportunity_id": str(opportunity.pk),
            "signal_count": len(signals),
        },
        reason_key="qualified_opportunity_research_requested",
        request_id=request_id,
        pipeline_run=pipeline,
    )
    return ScheduledResearch(research_run=research_run, outbox=outbox, created=True)


def _validate_envelope(envelope: TaskEnvelopeV2, command_type: str) -> ResearchRun:
    if envelope.command_type != command_type:
        raise ResearchValidationError("Unsupported research command type.")
    research_run = ResearchRun.objects.select_related(
        "pipeline_run", "opportunity", "opportunity__company"
    ).get(pk=envelope.object_id, pipeline_run_id=envelope.pipeline_run_id)
    outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=research_run.pipeline_run)
    if outbox.idempotency_key != envelope.idempotency_key:
        raise ResearchValidationError("Envelope idempotency does not match the outbox command.")
    return research_run


def _report_has_contract(report: str) -> bool:
    lowered = report.casefold()
    return all(heading.casefold() in lowered for heading in REQUIRED_REPORT_HEADINGS)


def _source_type(hostname: str, primary_domain: str) -> str:
    if primary_domain and (hostname == primary_domain or hostname.endswith(f".{primary_domain}")):
        return ResearchSourceType.OFFICIAL_COMPANY
    if hostname.endswith((".gov", ".gov.uk", ".bund.de", ".europa.eu")):
        return ResearchSourceType.OFFICIAL_GOVERNMENT
    if hostname in {"handelsregister.de", "unternehmensregister.de", "northdata.de"}:
        return ResearchSourceType.OFFICIAL_REGISTRY
    return ResearchSourceType.PUBLIC_OTHER


def _citation_locations(
    annotations: tuple[dict[str, object], ...], exact_url: str
) -> list[dict[str, object]]:
    locations: list[dict[str, object]] = []
    for item in annotations:
        if item.get("url") != exact_url:
            continue
        locations.append(
            {
                key: item[key]
                for key in ("start_index", "end_index", "title")
                if key in item and isinstance(item[key], (str, int))
            }
        )
    return locations[:100]


def _register_sources(
    research_run: ResearchRun,
    result_sources: tuple[ProviderSourceV1, ...],
    citations: tuple[dict[str, object], ...],
) -> tuple[ResearchSource, ...]:
    public_payload = cast(dict[str, object], research_run.public_input_payload)
    company_payload = cast(dict[str, object], public_payload.get("company", {}))
    primary_domain = str(company_payload.get("primary_domain", ""))
    normalized: dict[str, tuple[str, str, str]] = {}
    for raw in result_sources:
        exact_url = str(raw.url)
        canonical = canonicalize_url(exact_url, settings.RUNTIME_SETTINGS.fetch)
        try:
            ipaddress.ip_address(canonical.hostname_ascii)
        except ValueError:
            pass
        else:
            raise ResearchValidationError("Literal-IP research source URLs are prohibited.")
        normalized[canonical.sha256] = (
            exact_url,
            canonical.canonical,
            canonical.hostname_ascii,
        )
    if not normalized:
        raise ResearchValidationError("The public report has no registrable sources.")
    registered: list[ResearchSource] = []
    source_by_url = {str(item.url): item for item in result_sources}
    for ordinal, (url_hash, values) in enumerate(sorted(normalized.items()), start=1):
        exact_url, canonical_url, hostname = values
        raw = source_by_url[exact_url]
        title = str(getattr(raw, "title", ""))[:1_000]
        source_reference = str(getattr(raw, "source_reference", ""))[:500]
        registered.append(
            ResearchSource.objects.create(
                research_run=research_run,
                public_id=f"SRC-{ordinal:06d}",
                exact_provider_url=exact_url,
                canonical_url=canonical_url,
                canonical_url_sha256=url_hash,
                title=title,
                publisher=hostname[:500],
                source_type=_source_type(hostname, primary_domain),
                retrieved_at=timezone.now(),
                provider_reference={"source_reference": source_reference},
                citation_locations=_citation_locations(citations, exact_url),
            )
        )
    return tuple(registered)


def execute_public_research(
    envelope: TaskEnvelopeV2, *, provider: StandardResearchProvider | None = None
) -> bool:
    with transaction.atomic():
        research_run = _validate_envelope(envelope, RESEARCH_PUBLIC_COMMAND_TYPE)
        effect_key = f"{envelope.idempotency_key}:effect"
        if PipelineStepRun.objects.filter(idempotency_key=effect_key).exists():
            return False
        if research_run.status not in {
            ResearchRunStatus.QUEUED,
            ResearchRunStatus.IN_PROGRESS,
        }:
            raise ResearchValidationError("The research run is not ready for public research.")
        now = timezone.now()
        research_run.status = ResearchRunStatus.IN_PROGRESS
        research_run.started_at = research_run.started_at or now
        research_run.save(update_fields=("status", "started_at", "updated_at"))
        pipeline = research_run.pipeline_run
        pipeline.status = PipelineStatus.RUNNING
        pipeline.stage = "public_research_running"
        pipeline.started_at = pipeline.started_at or now
        pipeline.heartbeat_at = now
        pipeline.attempts += 1
        pipeline.row_version += 1
        pipeline.save(
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
        opportunity = research_run.opportunity
        opportunity.research_status = ResearchStatus.IN_PROGRESS
        opportunity.row_version += 1
        opportunity.save(update_fields=("research_status", "row_version", "updated_at"))
        request = WebResearchRequestV2.model_validate_json(
            json.dumps(research_run.public_input_payload)
        )
        policy = active_model_policy(research_run.public_policy_key)
    api_key = settings.RUNTIME_SETTINGS.openai_api_key
    if provider is None:
        if api_key is None:
            raise ResearchRequestError("The configured provider API key is unavailable.")
        active_provider: StandardResearchProvider = OpenAIResponsesProvider(
            api_key=api_key.get_secret_value()
        )
    else:
        active_provider = provider
    result = active_provider.web_research(request, policy=policy, pipeline_run=pipeline)
    report_bytes = result.report_markdown.encode("utf-8")
    if len(report_bytes) > REPORT_MAX_BYTES:
        raise ResearchValidationError("The public research report exceeds the storage limit.")
    if not _report_has_contract(result.report_markdown):
        raise ResearchValidationError("The public report is missing required section headings.")
    report_hash = _sha256_bytes(report_bytes)
    storage_key = f"research/reports/{research_run.pk}/{report_hash}.md"
    if not default_storage.exists(storage_key):
        saved_key = default_storage.save(storage_key, ContentFile(report_bytes))
        if saved_key != storage_key:
            raise ResearchValidationError("Storage changed the deterministic report key.")
    with transaction.atomic():
        research_run = (
            ResearchRun.objects.select_for_update()
            .select_related("pipeline_run", "opportunity")
            .get(pk=research_run.pk)
        )
        if PipelineStepRun.objects.filter(idempotency_key=effect_key).exists():
            return False
        ResearchReportArtifact.objects.create(
            research_run=research_run,
            storage_key=storage_key,
            sha256=report_hash,
            size_bytes=len(report_bytes),
        )
        sources = _register_sources(research_run, result.sources, result.citation_annotations)
        registry_payload = [
            {
                "source_id": source.public_id,
                "canonical_url": source.canonical_url,
                "url_sha256": source.canonical_url_sha256,
                "type": source.source_type,
            }
            for source in sources
        ]
        provider_call = ProviderCall.objects.get(
            pipeline_run=research_run.pipeline_run,
            provider="openai",
            operation="research.web_search",
            external_response_id=result.response_id,
        )
        now = timezone.now()
        research_run.status = ResearchRunStatus.EXTRACTING
        research_run.source_registry_sha256 = _sha256_payload(registry_payload)
        research_run.public_provider_call = provider_call
        research_run.source_completed_at = now
        research_run.save(
            update_fields=(
                "status",
                "source_registry_sha256",
                "public_provider_call",
                "source_completed_at",
                "updated_at",
            )
        )
        PipelineStepRun.objects.create(
            pipeline_run=research_run.pipeline_run,
            stage="public_research",
            status=StepStatus.COMPLETE,
            idempotency_key=effect_key,
            started_at=research_run.started_at,
            heartbeat_at=now,
            completed_at=now,
            input_ids={"research_run_id": str(research_run.pk)},
            output_ids={
                "report_artifact_id": str(research_run.report_artifact.pk),
                "source_ids": [source.public_id for source in sources],
            },
        )
        extraction_key = f"{research_run.idempotency_key}:extract"
        extraction_payload = TargetCommandPayloadV1(
            pipeline_run_id=research_run.pipeline_run_id,
            object_id=research_run.pk,
        )
        outbox = TaskOutbox(
            command_type=RESEARCH_EXTRACT_COMMAND_TYPE,
            payload=extraction_payload.model_dump(mode="json"),
            payload_schema_version="1.0",
            idempotency_key=extraction_key,
            pipeline_run=research_run.pipeline_run,
            request_id=research_run.pipeline_run.request_id,
            available_at=now,
        )
        outbox.full_clean()
        outbox.save()
        pipeline = research_run.pipeline_run
        pipeline.stage = "research_extraction_queued"
        pipeline.heartbeat_at = now
        pipeline.output_count = len(sources)
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
        AuditEvent.objects.create(
            actor_type=ActorType.PROVIDER,
            action="research.public_report_registered",
            object_type="research_run",
            object_id=research_run.pk,
            after_summary={
                "status": research_run.status,
                "source_count": len(sources),
                "report_sha256": report_hash,
            },
            reason_key="cited_public_report_completed",
            request_id=pipeline.request_id,
            pipeline_run=pipeline,
        )
    return True


def read_report_text(artifact: ResearchReportArtifact) -> str:
    with default_storage.open(artifact.storage_key, "rb") as stored:
        report_bytes = cast(bytes, stored.read(REPORT_MAX_BYTES + 1))
    if len(report_bytes) != artifact.size_bytes or len(report_bytes) > REPORT_MAX_BYTES:
        raise ResearchValidationError("The persisted report size does not match its metadata.")
    if _sha256_bytes(report_bytes) != artifact.sha256:
        raise ResearchValidationError("The persisted report hash does not match its metadata.")
    return report_bytes.decode("utf-8")


def _extraction_request(research_run: ResearchRun) -> ResearchExtractionRequestV2:
    report = read_report_text(research_run.report_artifact)
    sources = tuple(
        RegisteredSourceV2(
            source_id=source.public_id,
            canonical_url=source.canonical_url,
            title=source.title or source.publisher,
            publisher=source.publisher,
            retrieved_at=source.retrieved_at.isoformat(),
            source_type=source.source_type,
        )
        for source in research_run.sources.all()
    )
    facts = cast(list[dict[str, object]], research_run.brief_payload["known_observed_facts"])
    signal_ids = tuple(UUID(str(item["signal_id"])) for item in facts)
    evidence_ids = tuple(
        sorted(
            {
                str(evidence_id)
                for item in facts
                for evidence_id in cast(list[object], item["evidence_ids"])
            }
        )
    )
    return ResearchExtractionRequestV2(
        schema_version="2.1",
        research_run_id=research_run.pk,
        report_markdown=report,
        registered_sources=sources,
        known_signal_ids=signal_ids,
        known_evidence_ids=evidence_ids,
        max_claims=40,
        stale_after_days=STALE_AFTER_DAYS,
    )


def _validate_extraction(
    research_run: ResearchRun,
    output: ResearchExtractionV2,
) -> tuple[dict[str, ResearchSource], dict[UUID, SignalEvent]]:
    source_map = {source.public_id: source for source in research_run.sources.all()}
    facts = cast(list[dict[str, object]], research_run.brief_payload["known_observed_facts"])
    known_signal_ids = {UUID(str(item["signal_id"])) for item in facts}
    signal_map = {
        signal.pk: signal
        for signal in SignalEvent.objects.filter(pk__in=known_signal_ids).prefetch_related(
            "evidence_links__evidence_item"
        )
    }
    if set(signal_map) != known_signal_ids:
        raise ResearchValidationError("A selected signal is no longer available.")
    claim_keys: set[str] = set()
    for claim in output.claims:
        if claim.claim_key in claim_keys:
            raise ResearchValidationError("The extraction contains duplicate claim keys.")
        claim_keys.add(claim.claim_key)
        if (
            claim.claim_type in {ClaimType.OBSERVED_FACT, ClaimType.INFERENCE}
            and not claim.source_ids
        ):
            raise ResearchValidationError("Observed facts and inferences require a source.")
        if not set(claim.source_ids).issubset(source_map):
            raise ResearchValidationError("The extraction references an unregistered source.")
        if not set(claim.signal_ids).issubset(known_signal_ids):
            raise ResearchValidationError("The extraction references an unselected signal.")
        if claim.evidence_ids:
            if len(claim.signal_ids) != 1:
                raise ResearchValidationError(
                    "Evidence IDs require exactly one signal because catalogs are local."
                )
            signal = signal_map[claim.signal_ids[0]]
            known_evidence = {link.evidence_item.public_id for link in signal.evidence_links.all()}
            if not set(claim.evidence_ids).issubset(known_evidence):
                raise ResearchValidationError(
                    "The extraction references evidence outside its signal catalog."
                )
        if claim.expires_at and claim.current_as_of and claim.expires_at < claim.current_as_of:
            raise ResearchValidationError("A claim expiry precedes its current-as-of date.")
        if any(pattern.search(claim.statement) for pattern in PROHIBITED_CLAIM_PATTERNS):
            raise ResearchValidationError("The extraction crossed a research-stage boundary.")
    categorized = (
        output.ownership_context_claim_ids
        + output.external_partner_context_claim_ids
        + output.infrastructure_context_claim_ids
        + output.evidence_against_claim_ids
    )
    if not set(categorized).issubset(claim_keys):
        raise ResearchValidationError("A categorized claim reference is not present.")
    for conflict in output.conflicts:
        if not set(conflict.claim_keys).issubset(claim_keys):
            raise ResearchValidationError("A conflict references an unknown claim.")
        if not set(conflict.source_ids).issubset(source_map):
            raise ResearchValidationError("A conflict references an unregistered source.")
    return source_map, signal_map


def _render_dossier(output: ResearchExtractionV2, claims: list[ResearchClaim]) -> str:
    lines = [
        "# Company research dossier",
        "",
        "## Executive summary",
        "",
        output.executive_summary,
        "",
        "## Registered claims",
        "",
    ]
    for claim in claims:
        references = ", ".join(claim.source_ids + claim.signal_ids + claim.evidence_ids)
        lines.extend(
            (
                f"### {claim.public_id} · {claim.get_claim_type_display()}",
                "",
                claim.statement,
                "",
                f"Category: {claim.claim_category}; confidence: {claim.confidence}; "
                f"references: {references or 'none'}",
                "",
            )
        )
    lines.extend(("## Material unknowns", ""))
    lines.extend(f"- {unknown}" for unknown in output.unknowns)
    lines.extend(("", "## Review flags", ""))
    lines.extend(f"- {flag}" for flag in output.review_flags)
    return "\n".join(lines).strip() + "\n"


def execute_research_extraction(
    envelope: TaskEnvelopeV2, *, provider: StandardResearchProvider | None = None
) -> bool:
    with transaction.atomic():
        research_run = _validate_envelope(envelope, RESEARCH_EXTRACT_COMMAND_TYPE)
        effect_key = f"{envelope.idempotency_key}:effect"
        if PipelineStepRun.objects.filter(idempotency_key=effect_key).exists():
            return False
        if research_run.status != ResearchRunStatus.EXTRACTING:
            raise ResearchValidationError("The research run is not ready for extraction.")
        request = _extraction_request(research_run)
        policy = active_model_policy(research_run.extraction_policy_key)
        pipeline = research_run.pipeline_run
        pipeline.stage = "research_extraction_running"
        pipeline.heartbeat_at = timezone.now()
        pipeline.row_version += 1
        pipeline.save(update_fields=("stage", "heartbeat_at", "row_version", "updated_at"))
    api_key = settings.RUNTIME_SETTINGS.openai_api_key
    if provider is None:
        if api_key is None:
            raise ResearchRequestError("The configured provider API key is unavailable.")
        active_provider: StandardResearchProvider = OpenAIResponsesProvider(
            api_key=api_key.get_secret_value()
        )
    else:
        active_provider = provider
    result = active_provider.research_extraction(request, policy=policy, pipeline_run=pipeline)
    with transaction.atomic():
        research_run = (
            ResearchRun.objects.select_for_update()
            .select_related("pipeline_run", "opportunity")
            .get(pk=research_run.pk)
        )
        if PipelineStepRun.objects.filter(idempotency_key=effect_key).exists():
            return False
        source_map, signal_map = _validate_extraction(research_run, result.output)
        created_claims: list[ResearchClaim] = []
        claim_key_map: dict[str, str] = {}
        for ordinal, extracted in enumerate(result.output.claims, start=1):
            public_id = f"CLM-{ordinal:06d}"
            claim_key_map[extracted.claim_key] = public_id
            claim = ResearchClaim.objects.create(
                research_run=research_run,
                public_id=public_id,
                claim_type=extracted.claim_type,
                claim_category=extracted.claim_category,
                statement=extracted.statement,
                source_ids=list(extracted.source_ids),
                signal_ids=[str(value) for value in extracted.signal_ids],
                evidence_ids=list(extracted.evidence_ids),
                confidence=extracted.confidence,
                current_as_of=extracted.current_as_of,
                expires_at=extracted.expires_at,
                conflict_group=extracted.conflict_group or "",
            )
            created_claims.append(claim)
            ResearchClaimSource.objects.bulk_create(
                [
                    ResearchClaimSource(claim=claim, source=source_map[source_id])
                    for source_id in extracted.source_ids
                ]
            )
            ResearchClaimSignal.objects.bulk_create(
                [
                    ResearchClaimSignal(claim=claim, signal=signal_map[signal_id])
                    for signal_id in extracted.signal_ids
                ]
            )
            evidence_links: list[ResearchClaimEvidence] = []
            if extracted.evidence_ids:
                signal = signal_map[extracted.signal_ids[0]]
                evidence_map = {
                    link.evidence_item.public_id: link.evidence_item
                    for link in signal.evidence_links.all()
                }
                evidence_links = [
                    ResearchClaimEvidence(claim=claim, evidence_item=evidence_map[evidence_id])
                    for evidence_id in extracted.evidence_ids
                ]
            ResearchClaimEvidence.objects.bulk_create(evidence_links)
        dossier_text = _render_dossier(result.output, created_claims)
        ResearchDossier.objects.create(
            research_run=research_run,
            markdown_text=dossier_text,
            markdown_sha256=_sha256_bytes(dossier_text.encode()),
            renderer_version=DOSSIER_RENDERER_VERSION,
        )
        provider_call = ProviderCall.objects.get(
            pipeline_run=research_run.pipeline_run,
            provider="openai",
            operation="research.extract",
            external_response_id=result.response_id,
        )
        now = timezone.now()
        expires_at = now + timedelta(days=STALE_AFTER_DAYS)
        extraction_payload = result.output.model_dump(mode="json")
        extraction_payload["local_claim_id_map"] = claim_key_map
        research_run.status = ResearchRunStatus.COMPLETE
        research_run.extraction_output = extraction_payload
        research_run.extraction_provider_call = provider_call
        research_run.completed_at = now
        research_run.expires_at = expires_at
        research_run.error_code = ""
        research_run.safe_error_message = ""
        research_run.save(
            update_fields=(
                "status",
                "extraction_output",
                "extraction_provider_call",
                "completed_at",
                "expires_at",
                "error_code",
                "safe_error_message",
                "updated_at",
            )
        )
        PipelineStepRun.objects.create(
            pipeline_run=research_run.pipeline_run,
            stage="research_extraction",
            status=StepStatus.COMPLETE,
            idempotency_key=effect_key,
            started_at=now,
            heartbeat_at=now,
            completed_at=now,
            input_ids={
                "report_artifact_id": str(research_run.report_artifact.pk),
                "source_registry_sha256": research_run.source_registry_sha256,
            },
            output_ids={
                "claim_ids": [claim.public_id for claim in created_claims],
                "dossier_id": str(research_run.dossier.pk),
            },
        )
        pipeline = research_run.pipeline_run
        pipeline.status = PipelineStatus.COMPLETE
        pipeline.stage = "research_complete"
        pipeline.completed_at = now
        pipeline.heartbeat_at = now
        pipeline.output_count = len(created_claims)
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
        opportunity = research_run.opportunity
        opportunity.research_status = ResearchStatus.COMPLETE
        opportunity.next_action_key = "solution_design"
        opportunity.row_version += 1
        opportunity.save(
            update_fields=(
                "research_status",
                "next_action_key",
                "row_version",
                "updated_at",
            )
        )
        AuditEvent.objects.create(
            actor_type=ActorType.PROVIDER,
            action="research.standard_completed",
            object_type="research_run",
            object_id=research_run.pk,
            after_summary={
                "status": research_run.status,
                "claim_count": len(created_claims),
                "source_count": len(source_map),
                "dossier_sha256": research_run.dossier.markdown_sha256,
            },
            reason_key="validated_no_web_extraction",
            request_id=pipeline.request_id,
            pipeline_run=pipeline,
        )
    return True


def _failure_code(error: Exception, *, extraction: bool) -> str:
    if isinstance(error, ProviderBudgetBlocked):
        return "RESEARCH_BUDGET_BLOCKED"
    if isinstance(error, ProviderRefused):
        return "PROVIDER_REFUSAL"
    if isinstance(error, ProviderIncomplete):
        return "PROVIDER_INCOMPLETE"
    if isinstance(error, ProviderSchemaInvalid):
        return "EXTRACTION_SCHEMA_INVALID" if extraction else "PUBLIC_REPORT_INVALID"
    if isinstance(error, SourcePolicyError):
        return "SOURCE_REGISTRY_INVALID"
    if isinstance(error, ResearchValidationError):
        return "EXTRACTION_REFERENCE_INVALID" if extraction else "PUBLIC_REPORT_INVALID"
    if isinstance(error, ProviderError):
        return "EXTRACTION_PROVIDER_FAILED" if extraction else "WEB_RESEARCH_FAILED"
    return "RESEARCH_FAILED"


@transaction.atomic
def mark_research_failed(*, pipeline_run_id: UUID, error: Exception, extraction: bool) -> None:
    pipeline = PipelineRun.objects.select_for_update().get(pk=pipeline_run_id)
    if pipeline.status == PipelineStatus.COMPLETE:
        return
    research_run = (
        ResearchRun.objects.select_for_update()
        .select_related("opportunity")
        .get(pipeline_run=pipeline)
    )
    has_report = ResearchReportArtifact.objects.filter(research_run=research_run).exists()
    status = ResearchRunStatus.PARTIAL if has_report else ResearchRunStatus.FAILED
    opportunity_status = ResearchStatus.PARTIAL if has_report else ResearchStatus.FAILED
    code = _failure_code(error, extraction=extraction)
    now = timezone.now()
    message = _safe_message(error)
    research_run.status = status
    research_run.error_code = code
    research_run.safe_error_message = message
    research_run.completed_at = now
    research_run.save(
        update_fields=(
            "status",
            "error_code",
            "safe_error_message",
            "completed_at",
            "updated_at",
        )
    )
    pipeline.status = PipelineStatus.FAILED
    pipeline.stage = "research_extraction_failed" if extraction else "public_research_failed"
    pipeline.completed_at = now
    pipeline.heartbeat_at = now
    pipeline.error_count += 1
    pipeline.last_error_code = code
    pipeline.last_error_message = message
    pipeline.row_version += 1
    pipeline.save(
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
    opportunity = research_run.opportunity
    opportunity.research_status = opportunity_status
    opportunity.next_action_key = "review_partial_research" if has_report else "retry_research"
    opportunity.row_version += 1
    opportunity.save(
        update_fields=(
            "research_status",
            "next_action_key",
            "row_version",
            "updated_at",
        )
    )
    AuditEvent.objects.create(
        actor_type=ActorType.SYSTEM,
        action="research.standard_failed",
        object_type="research_run",
        object_id=research_run.pk,
        after_summary={"status": status, "error_code": code, "report_preserved": has_report},
        reason_key=code.casefold(),
        request_id=pipeline.request_id,
        pipeline_run=pipeline,
    )
