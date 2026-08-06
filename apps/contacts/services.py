from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, cast
from urllib.parse import unquote, urljoin, urlsplit
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from pydantic import SecretStr

from apps.companies.models import Company
from apps.contacts.contracts import (
    BuyerRoleHypothesisV2,
    BuyerRoleResultV2,
    ContactRouteItemV2,
    ContactRouteResultV2,
)
from apps.contacts.models import (
    BuyerRoleHypothesis,
    BuyerRoleResult,
    ContactEvidence,
    ContactObservation,
    ContactPerson,
    ContactResearchRun,
    ContactResearchStatus,
    ContactRoute,
    ContactSelection,
    ContactSourceArtifact,
    ContactSourceTarget,
    ContactSourceTargetStatus,
    RouteOrigin,
    RouteType,
    SuppressionEntry,
)
from apps.operations.commands import (
    BUYER_ROLES_INFER_COMMAND_TYPE,
    CONTACT_SOURCE_SCAN_COMMAND_TYPE,
)
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
from apps.opportunities.models import Opportunity
from apps.research.models import ResearchSource, ResearchSourceType
from apps.solutions.models import OpportunitySolutionState, SolutionStateStatus, SolutionVersion
from apps.sources.contracts import SafeFetchResultV1
from apps.sources.http import SafeFetchError, SafeHttpFetcher
from apps.sources.policy import SourcePolicyError, canonicalize_url, registrable_domain

BUYER_ROLE_PROMPT_VERSION = "2.1.0"
BUYER_ROLE_POLICY_VERSION = "deterministic-1.0.0"
ROUTE_EXTRACTOR_PROMPT_VERSION = "2.1.0"
ROUTE_EXTRACTOR_VERSION = "deterministic-html-1.0.0"
MAX_CONTACT_SOURCES = 10
GENERIC_ROLE_EMAIL_LOCAL_PARTS = {
    "contact",
    "hello",
    "hi",
    "info",
    "office",
    "sales",
    "team",
    "partnerships",
    "business",
}
HUMAN_ROUTE_TYPES = {
    RouteType.WARM_INTRODUCTION,
    RouteType.EXISTING_RELATIONSHIP,
    RouteType.EVENT_CONNECTION,
}
PUBLIC_ROUTE_TYPES = {
    RouteType.ROLE_EMAIL,
    RouteType.INDIVIDUAL_BUSINESS_EMAIL,
    RouteType.CONTACT_FORM,
    RouteType.PROFESSIONAL_PROFILE,
    RouteType.PHONE,
    RouteType.OTHER_PUBLIC_ROUTE,
}
EMAIL_RE = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,63}$", re.I)
MAILTO_RE = re.compile(r"(?is)\bhref\s*=\s*(?P<q>[\"'])(?P<value>mailto:[^\"']+)(?P=q)")
TEL_RE = re.compile(r"(?is)\bhref\s*=\s*(?P<q>[\"'])(?P<value>tel:[^\"']+)(?P=q)")
FORM_RE = re.compile(
    r"(?is)<form\b(?P<tag>[^>]*\baction\s*=\s*(?P<q>[\"'])(?P<value>.*?)(?P=q)[^>]*)>"
)
LINK_RE = re.compile(r"(?is)\bhref\s*=\s*(?P<q>[\"'])(?P<value>(?:https?://|/)[^\"']*)(?P=q)")
CONTACT_PATH_RE = re.compile(
    r"(?:^|[/_-])(contact|kontakt|connect|inquiry|inquiries)(?:[/_.-]|$)", re.I
)
UNTRUSTED_NONCONTENT_RE = re.compile(
    r"(?is)<!--.*?-->|<(?:script|style|template|noscript)\b.*?</(?:script|style|template|noscript)\s*>"
)


class ContactValidationError(ValueError):
    pass


class ContactConfigurationError(ContactValidationError):
    pass


class ContactFetcher(Protocol):
    def fetch(
        self, requested_url: str, *, etag: str = "", last_modified: str = ""
    ) -> SafeFetchResultV1: ...


@dataclass(frozen=True)
class ScheduledContactResearch:
    contact_research_run: ContactResearchRun
    pipeline_run: PipelineRun
    outbox: TaskOutbox
    created: bool


def _sha256_payload(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _safe_message(error: Exception) -> str:
    return (str(error).replace("\n", " ").strip() or error.__class__.__name__)[:500]


def _require_permission(actor: User, permission: str) -> None:
    if not actor.is_active or not actor.has_perm(permission):
        raise ContactValidationError("The operator is not permitted to perform this action.")


def _decode_secret(secret: SecretStr | None, name: str) -> bytes:
    if secret is None:
        raise ContactConfigurationError(f"{name} is not configured.")
    value = secret.get_secret_value()
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ContactConfigurationError(f"{name} is invalid.") from exc
    if len(decoded) != 32:
        raise ContactConfigurationError(f"{name} must encode exactly 32 bytes.")
    return decoded


def _crypto_keys() -> tuple[bytes, bytes, str]:
    runtime = settings.RUNTIME_SETTINGS
    return (
        _decode_secret(runtime.contact_route_encryption_key, "Contact route encryption key"),
        _decode_secret(runtime.contact_route_hmac_key, "Contact route HMAC key"),
        runtime.contact_route_key_id,
    )


def _normalize_route_value(route_type: str, value: str) -> str:
    cleaned = html.unescape(value).strip()
    if route_type in {RouteType.ROLE_EMAIL, RouteType.INDIVIDUAL_BUSINESS_EMAIL}:
        email_value = unquote(cleaned.removeprefix("mailto:")).split("?", 1)[0].strip().casefold()
        if not EMAIL_RE.fullmatch(email_value):
            raise ContactValidationError("The source did not contain a valid literal email route.")
        return email_value
    if route_type == RouteType.PHONE:
        phone = unquote(cleaned.removeprefix("tel:")).strip()
        normalized = ("+" if phone.startswith("+") else "") + "".join(
            character for character in phone if character.isdecimal()
        )
        if len(normalized.lstrip("+")) < 6 or len(normalized.lstrip("+")) > 20:
            raise ContactValidationError("The source did not contain a valid literal phone route.")
        return normalized
    if route_type in {
        RouteType.CONTACT_FORM,
        RouteType.PROFESSIONAL_PROFILE,
        RouteType.OTHER_PUBLIC_ROUTE,
    }:
        try:
            return canonicalize_url(cleaned, settings.RUNTIME_SETTINGS.fetch).canonical
        except SourcePolicyError as exc:
            raise ContactValidationError(exc.safe_message) from exc
    normalized = " ".join(cleaned.split())
    if len(normalized) < 3:
        raise ContactValidationError("The human-origin route description is too short.")
    return normalized


def _route_hmac(normalized: str, hmac_key: bytes) -> str:
    return hmac.new(hmac_key, normalized.encode(), hashlib.sha256).hexdigest()


def _encrypt_value(normalized: str, encryption_key: bytes, associated_data: bytes) -> str:
    nonce = os.urandom(12)
    encrypted = AESGCM(encryption_key).encrypt(nonce, normalized.encode(), associated_data)
    return base64.urlsafe_b64encode(nonce + encrypted).decode()


def _encrypt_bytes(value: bytes, encryption_key: bytes, associated_data: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(encryption_key).encrypt(nonce, value, associated_data)


def decrypt_route_value(route: ContactRoute) -> str:
    if route.public_value:
        return route.public_value
    encryption_key, _hmac_key, key_id = _crypto_keys()
    if route.key_id != key_id:
        raise ContactConfigurationError("The active contact key cannot decrypt this key version.")
    payload = base64.urlsafe_b64decode(route.encrypted_value.encode())
    associated_data = f"{route.company_id}:{route.route_type}:{route.key_id}".encode()
    try:
        return AESGCM(encryption_key).decrypt(payload[:12], payload[12:], associated_data).decode()
    except Exception as exc:
        raise ContactConfigurationError(
            "The protected contact route could not be decrypted."
        ) from exc


def _masked_value(route_type: str, normalized: str) -> str:
    if route_type in {RouteType.ROLE_EMAIL, RouteType.INDIVIDUAL_BUSINESS_EMAIL}:
        local, domain = normalized.split("@", 1)
        return f"{local[:1]}***@{domain}"
    if route_type == RouteType.PHONE:
        return f"***{normalized[-4:]}"
    if route_type in HUMAN_ROUTE_TYPES:
        return "Protected human-origin route"
    return normalized[:500]


def _is_suppressed(*, company: Company, route_hmac: str, person: ContactPerson | None) -> bool:
    query = SuppressionEntry.objects.filter(active=True)
    return (
        query.filter(scope_type="company", company=company).exists()
        or query.filter(scope_type="route", normalized_hmac=route_hmac).exists()
        or bool(person and query.filter(scope_type="person", contact_person=person).exists())
    )


def _store_route(
    *,
    company: Company,
    buyer_role: BuyerRoleHypothesis | None,
    route_type: str,
    route_origin: str,
    value: str,
    confidence: float,
    observation_status: str,
    freshness_status: str,
    research_source: ResearchSource | None,
    evidence: ContactEvidence | None,
    source_ids: list[str],
    evidence_ids: list[str],
    actor: User | None,
    provenance_note: str,
    retrieved_at: datetime,
    person: ContactPerson | None = None,
) -> tuple[ContactRoute, bool]:
    encryption_key, hmac_key, key_id = _crypto_keys()
    normalized = _normalize_route_value(route_type, value)
    normalized_hmac = _route_hmac(normalized, hmac_key)
    existing = ContactRoute.objects.filter(company=company, normalized_hmac=normalized_hmac).first()
    if existing is not None:
        existing.last_checked_at = retrieved_at
        existing.row_version += 1
        existing.save(update_fields=("last_checked_at", "row_version", "updated_at"))
        return existing, False
    public = route_type in {
        RouteType.CONTACT_FORM,
        RouteType.PROFESSIONAL_PROFILE,
        RouteType.OTHER_PUBLIC_ROUTE,
    }
    encrypted_value = ""
    public_value = normalized if public else ""
    if not public:
        associated_data = f"{company.pk}:{route_type}:{key_id}".encode()
        encrypted_value = _encrypt_value(normalized, encryption_key, associated_data)
    suppressed = _is_suppressed(company=company, route_hmac=normalized_hmac, person=person)
    route = ContactRoute.objects.create(
        company=company,
        contact_person=person,
        buyer_role=buyer_role,
        route_type=route_type,
        route_origin=route_origin,
        public_value=public_value,
        encrypted_value=encrypted_value,
        value_masked=_masked_value(route_type, normalized),
        normalized_hmac=normalized_hmac,
        key_id=key_id,
        primary_research_source=research_source,
        primary_evidence=evidence,
        source_ids=source_ids,
        evidence_ids=evidence_ids,
        created_by=actor,
        provenance_note=provenance_note,
        retrieved_at=retrieved_at,
        last_checked_at=retrieved_at,
        observation_status=observation_status,
        freshness_status=freshness_status,
        deliverability_status="unknown",
        outreach_eligibility="suppressed" if suppressed else "unreviewed",
        recommendation="do_not_contact" if suppressed else "research_more",
        confidence=Decimal(str(confidence)),
    )
    return route, True


@transaction.atomic
def request_contact_research(
    *, opportunity_id: UUID, actor: User, request_id: UUID | None = None
) -> ScheduledContactResearch:
    _require_permission(actor, "contacts.request_contact_research")
    if not settings.RUNTIME_SETTINGS.features.contact_route_research_enabled:
        raise ContactValidationError("Automated public contact-route research is disabled.")
    opportunity = (
        Opportunity.objects.select_for_update().select_related("company").get(pk=opportunity_id)
    )
    state = OpportunitySolutionState.objects.select_related("approved_version").get(
        opportunity=opportunity
    )
    solution = state.approved_version
    if state.status != SolutionStateStatus.APPROVED or solution is None:
        raise ContactValidationError("An exact approved current solution is required.")
    if not hasattr(solution, "asset_match"):
        raise ContactValidationError("A completed asset match, including zero assets, is required.")
    fingerprint = {
        "opportunity_id": str(opportunity.pk),
        "solution_id": str(solution.pk),
        "solution_hash": solution.output_sha256,
        "asset_match_hash": solution.asset_match.output_sha256,
        "buyer_role_policy": BUYER_ROLE_POLICY_VERSION,
        "route_extractor": ROUTE_EXTRACTOR_VERSION,
    }
    input_sha256 = _sha256_payload(fingerprint)
    idempotency_key = f"contacts.enrich:{opportunity.pk}:{input_sha256}"
    pipeline, created = PipelineRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "pipeline_name": "contacts.enrich",
            "stage": "buyer_roles_queued",
            "status": PipelineStatus.QUEUED,
            "trigger": PipelineTrigger.MANUAL,
            "requested_by": actor,
            "request_id": request_id,
            "object_type": "opportunity",
            "object_id": opportunity.pk,
            "heartbeat_at": timezone.now(),
            "input_count": 1,
            "policy_versions": {
                "buyer_role_prompt": BUYER_ROLE_PROMPT_VERSION,
                "buyer_role_policy": BUYER_ROLE_POLICY_VERSION,
                "route_extractor": ROUTE_EXTRACTOR_VERSION,
            },
            "context": {"solution_version_id": str(solution.pk)},
        },
    )
    if not created:
        return ScheduledContactResearch(
            contact_research_run=ContactResearchRun.objects.get(pipeline_run=pipeline),
            pipeline_run=pipeline,
            outbox=pipeline.outbox_commands.get(idempotency_key=f"{idempotency_key}:roles"),
            created=False,
        )
    contact_run = ContactResearchRun.objects.create(
        opportunity=opportunity,
        solution_version=solution,
        pipeline_run=pipeline,
        requested_by=actor,
        input_sha256=input_sha256,
    )
    payload = TargetCommandPayloadV1(pipeline_run_id=pipeline.pk, object_id=contact_run.pk)
    outbox = TaskOutbox.objects.create(
        command_type=BUYER_ROLES_INFER_COMMAND_TYPE,
        payload=payload.model_dump(mode="json"),
        payload_schema_version="1.0",
        idempotency_key=f"{idempotency_key}:roles",
        pipeline_run=pipeline,
        request_id=request_id,
        available_at=timezone.now(),
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="contacts.research_queued",
        object_type="opportunity",
        object_id=opportunity.pk,
        after_summary={"solution_version_id": str(solution.pk)},
        reason_key="approved_solution_contact_enrichment",
        request_id=request_id,
        pipeline_run=pipeline,
    )
    return ScheduledContactResearch(contact_run, pipeline, outbox, True)


def _validate_envelope(
    envelope: TaskEnvelopeV2, command_type: str
) -> tuple[PipelineRun, TaskOutbox]:
    if envelope.command_type != command_type:
        raise ContactValidationError("Unsupported contact command type.")
    pipeline = PipelineRun.objects.get(pk=envelope.pipeline_run_id)
    outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=pipeline)
    if outbox.idempotency_key != envelope.idempotency_key:
        raise ContactValidationError("Envelope idempotency does not match its outbox command.")
    return pipeline, outbox


def _claim_refs(solution: SolutionVersion) -> tuple[list[str], list[str], list[str]]:
    output = cast(dict[str, object], solution.structured_output)
    serialized = json.dumps(output, ensure_ascii=False)
    requested_claim_ids = set(re.findall(r"CLM-[0-9]{6}", serialized))
    claims = solution.research_run.claims.filter(public_id__in=requested_claim_ids)
    claim_ids: set[str] = set()
    source_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for claim in claims:
        claim_ids.add(claim.public_id)
        source_ids.update(cast(list[str], claim.source_ids))
        evidence_ids.update(cast(list[str], claim.evidence_ids))
    return sorted(source_ids), sorted(claim_ids), sorted(evidence_ids)


@transaction.atomic
def execute_buyer_role_inference(envelope: TaskEnvelopeV2) -> bool:
    pipeline, _outbox = _validate_envelope(envelope, BUYER_ROLES_INFER_COMMAND_TYPE)
    contact_run = (
        ContactResearchRun.objects.select_for_update()
        .select_related("solution_version__research_run", "opportunity__company")
        .get(pk=envelope.object_id, pipeline_run=pipeline)
    )
    if hasattr(contact_run, "buyer_role_result"):
        return False
    contact_run.status = ContactResearchStatus.RUNNING
    contact_run.started_at = contact_run.started_at or timezone.now()
    contact_run.row_version += 1
    contact_run.save(update_fields=("status", "started_at", "row_version", "updated_at"))
    pipeline.status = PipelineStatus.RUNNING
    pipeline.stage = "buyer_roles_in_progress"
    pipeline.heartbeat_at = timezone.now()
    pipeline.save(update_fields=("status", "stage", "heartbeat_at", "updated_at"))
    solution = contact_run.solution_version
    requirements = cast(
        list[dict[str, object]], solution.structured_output["buyer_role_requirements"]
    )
    source_ids, claim_ids, evidence_ids = _claim_refs(solution)
    roles: list[BuyerRoleHypothesisV2] = []
    seen: set[str] = set()
    for requirement in requirements:
        owner_type = str(requirement["owner_type"])
        if owner_type in seen:
            continue
        seen.add(owner_type)
        roles.append(
            BuyerRoleHypothesisV2(
                role_key=owner_type,
                owner_type=owner_type,  # type: ignore[arg-type]
                responsibility_match=str(requirement["responsibility"]),
                priority=len(roles) + 1,
                confidence=0.8 if claim_ids else 0.55,
                source_ids=tuple(source_ids),
                claim_ids=tuple(claim_ids),
                evidence_ids=tuple(evidence_ids),
                unknowns=("No person or final authority is inferred from this role category.",),
            )
        )
    if not roles:
        roles.append(
            BuyerRoleHypothesisV2(
                role_key="unknown",
                owner_type="unknown",
                responsibility_match=(
                    "Ownership requires human discovery against the approved solution."
                ),
                priority=1,
                confidence=0.2,
                source_ids=tuple(source_ids),
                claim_ids=tuple(claim_ids),
                evidence_ids=tuple(evidence_ids),
                unknowns=("The approved solution contains no supported ownership requirement.",),
            )
        )
    output = BuyerRoleResultV2(
        schema_version="2.1",
        prompt_version="2.1.0",
        solution_version_id=solution.pk,
        roles=tuple(roles),
        unknowns=("Named people, authority, and reporting lines remain unknown.",),
        review_flags=(),
    )
    output_payload = output.model_dump(mode="json")
    result = BuyerRoleResult.objects.create(
        contact_research_run=contact_run,
        solution_version=solution,
        output_payload=output_payload,
        input_sha256=contact_run.input_sha256,
        output_sha256=_sha256_payload(output_payload),
    )
    for ordinal, role in enumerate(output.roles, start=1):
        BuyerRoleHypothesis.objects.create(
            result=result,
            public_id=f"BR-{ordinal:06d}",
            role_key=role.role_key,
            owner_type=role.owner_type,
            responsibility_match=role.responsibility_match,
            priority=role.priority,
            confidence=Decimal(str(role.confidence)),
            source_ids=list(role.source_ids),
            claim_ids=list(role.claim_ids),
            evidence_ids=list(role.evidence_ids),
            unknowns=list(role.unknowns),
        )
    company_domains = {
        domain.registrable_domain
        for domain in contact_run.opportunity.company.domains.exclude(
            verification_status="disputed"
        )
    }
    sources = []
    for source in solution.research_run.sources.filter(
        source_type=ResearchSourceType.OFFICIAL_COMPANY
    ).order_by("public_id"):
        hostname = urlsplit(source.canonical_url).hostname or ""
        if registrable_domain(hostname) in company_domains:
            sources.append(source)
    for source in sources[:MAX_CONTACT_SOURCES]:
        target = ContactSourceTarget.objects.create(
            contact_research_run=contact_run,
            research_source=source,
            requested_url=source.canonical_url,
        )
        payload = TargetCommandPayloadV1(pipeline_run_id=pipeline.pk, object_id=target.pk)
        key = f"{pipeline.idempotency_key}:source:{source.pk}"
        TaskOutbox.objects.create(
            command_type=CONTACT_SOURCE_SCAN_COMMAND_TYPE,
            payload=payload.model_dump(mode="json"),
            payload_schema_version="1.0",
            idempotency_key=key,
            pipeline_run=pipeline,
            request_id=pipeline.request_id,
            available_at=timezone.now(),
        )
    PipelineStepRun.objects.create(
        pipeline_run=pipeline,
        stage="buyer_role_inference",
        status=StepStatus.COMPLETE,
        idempotency_key=f"{envelope.idempotency_key}:effect",
        started_at=contact_run.started_at,
        completed_at=timezone.now(),
        input_ids={"solution_version_id": str(solution.pk)},
        output_ids={"buyer_role_result_id": str(result.pk), "role_count": len(roles)},
    )
    if sources:
        pipeline.stage = "contact_sources_queued"
        pipeline.output_count = len(roles)
        pipeline.save(update_fields=("stage", "output_count", "updated_at"))
    else:
        now = timezone.now()
        contact_run.status = ContactResearchStatus.COMPLETE
        contact_run.completed_at = now
        contact_run.row_version += 1
        contact_run.save(update_fields=("status", "completed_at", "row_version", "updated_at"))
        pipeline.status = PipelineStatus.COMPLETE
        pipeline.stage = "contact_research_complete_no_sources"
        pipeline.completed_at = now
        pipeline.output_count = len(roles)
        pipeline.save(
            update_fields=("status", "stage", "completed_at", "output_count", "updated_at")
        )
    return True


def _evidence(
    artifact: ContactSourceArtifact,
    *,
    ordinal: int,
    kind: str,
    exact: str,
    normalized: str,
    start: int,
    end: int,
) -> ContactEvidence:
    encryption_key, _hmac_key, key_id = _crypto_keys()
    public_id = f"CEV-{ordinal:06d}"
    ciphertext = _encrypt_value(
        exact[:4_096],
        encryption_key,
        f"contact-evidence:{artifact.pk}:{public_id}:{key_id}".encode(),
    )
    public_normalized = (
        normalized
        if kind
        in {
            RouteType.CONTACT_FORM,
            RouteType.PROFESSIONAL_PROFILE,
            RouteType.OTHER_PUBLIC_ROUTE,
        }
        else ""
    )
    return ContactEvidence.objects.create(
        artifact=artifact,
        public_id=public_id,
        evidence_kind=kind,
        exact_text_ciphertext=ciphertext,
        display_text=_masked_value(kind, normalized),
        public_normalized_text=public_normalized[:4_096],
        encryption_key_id=key_id,
        start_offset=start,
        end_offset=end,
        exact_text_sha256=hashlib.sha256(exact.encode()).hexdigest(),
    )


def _candidate_routes(text: str, base_url: str) -> list[tuple[str, str, str, int, int]]:
    text = UNTRUSTED_NONCONTENT_RE.sub(lambda match: " " * len(match.group(0)), text)
    candidates: list[tuple[str, str, str, int, int]] = []
    seen: set[tuple[str, str]] = set()

    def add(route_type: str, raw: str, match: re.Match[str]) -> None:
        value = html.unescape(raw).strip()
        key = (route_type, value.casefold())
        if key not in seen:
            seen.add(key)
            candidates.append((route_type, value, match.group(0), match.start(), match.end()))

    for match in MAILTO_RE.finditer(text):
        literal = html.unescape(match.group("value"))
        address = unquote(literal.removeprefix("mailto:")).split("?", 1)[0].strip()
        if EMAIL_RE.fullmatch(address):
            local = address.split("@", 1)[0].casefold()
            route_type = (
                RouteType.ROLE_EMAIL
                if local in GENERIC_ROLE_EMAIL_LOCAL_PARTS
                else RouteType.INDIVIDUAL_BUSINESS_EMAIL
            )
            add(route_type, literal, match)
    for match in TEL_RE.finditer(text):
        add(RouteType.PHONE, match.group("value"), match)
    for match in FORM_RE.finditer(text):
        value = urljoin(base_url, html.unescape(match.group("value")).strip())
        if value.startswith(("https://", "http://")):
            add(RouteType.CONTACT_FORM, value, match)
    for match in LINK_RE.finditer(text):
        value = urljoin(base_url, html.unescape(match.group("value")).strip())
        path = urlsplit(value).path
        if CONTACT_PATH_RE.search(path):
            add(RouteType.CONTACT_FORM, value, match)
    return candidates[:100]


def _persist_contact_artifact(
    target: ContactSourceTarget, result: SafeFetchResultV1
) -> ContactSourceArtifact:
    existing = cast(
        ContactSourceArtifact | None,
        ContactSourceArtifact.objects.filter(target=target).first(),
    )
    if existing is not None:
        if existing.sha256 != result.body_sha256:
            raise ContactValidationError("A retried contact source returned different content.")
        return existing
    key = f"contacts/{target.pk}/{result.body_sha256}.source"
    encryption_key, _hmac_key, key_id = _crypto_keys()
    encrypted_body = _encrypt_bytes(
        result.body,
        encryption_key,
        f"contact-artifact:{target.pk}:{result.body_sha256}:{key_id}".encode(),
    )
    if not default_storage.exists(key):
        saved = default_storage.save(key, ContentFile(encrypted_body))
        if saved != key:
            raise ContactValidationError("Contact artifact storage changed its deterministic key.")
    return ContactSourceArtifact.objects.create(
        target=target,
        storage_key=key,
        requested_url=result.requested_url,
        final_url=result.final_url,
        sha256=result.body_sha256,
        size_bytes=result.body_size_bytes,
        content_type=result.content_type,
        storage_encrypted=True,
        encryption_key_id=key_id,
        retrieved_at=datetime.fromisoformat(result.retrieved_at_iso),
        status_code=result.status_code,
        redirect_chain=result.redirect_chain,
    )


def _settle_contact_run(contact_run_id: UUID) -> None:
    contact_run = (
        ContactResearchRun.objects.select_for_update()
        .select_related("pipeline_run", "opportunity")
        .get(pk=contact_run_id)
    )
    targets = list(contact_run.source_targets.all())
    if any(
        target.status in {ContactSourceTargetStatus.QUEUED, ContactSourceTargetStatus.RUNNING}
        for target in targets
    ):
        return
    failed = [target for target in targets if target.status == ContactSourceTargetStatus.FAILED]
    now = timezone.now()
    contact_run.status = (
        ContactResearchStatus.FAILED
        if failed and len(failed) == len(targets)
        else ContactResearchStatus.PARTIAL
        if failed
        else ContactResearchStatus.COMPLETE
    )
    contact_run.completed_at = now
    contact_run.row_version += 1
    contact_run.save(update_fields=("status", "completed_at", "row_version", "updated_at"))
    pipeline = contact_run.pipeline_run
    pipeline.status = (
        PipelineStatus.FAILED
        if contact_run.status == ContactResearchStatus.FAILED
        else PipelineStatus.COMPLETE
    )
    pipeline.stage = (
        "contact_research_failed"
        if pipeline.status == PipelineStatus.FAILED
        else "contact_research_complete"
    )
    pipeline.completed_at = now
    pipeline.output_count = sum(target.route_count for target in targets)
    pipeline.last_error_code = "CONTACT_SOURCE_FAILURE" if failed else ""
    pipeline.last_error_message = (
        f"{len(failed)} registered contact source(s) failed safely." if failed else ""
    )
    pipeline.save(
        update_fields=(
            "status",
            "stage",
            "completed_at",
            "output_count",
            "last_error_code",
            "last_error_message",
            "updated_at",
        )
    )
    opportunity = contact_run.opportunity
    opportunity.next_action_key = "review_contact_routes"
    opportunity.row_version += 1
    opportunity.save(update_fields=("next_action_key", "row_version", "updated_at"))


@transaction.atomic
def execute_contact_source_scan(
    envelope: TaskEnvelopeV2, *, fetcher: ContactFetcher | None = None
) -> bool:
    pipeline, _outbox = _validate_envelope(envelope, CONTACT_SOURCE_SCAN_COMMAND_TYPE)
    target = (
        ContactSourceTarget.objects.select_for_update()
        .select_related(
            "contact_research_run__opportunity__company",
            "research_source",
        )
        .get(pk=envelope.object_id, contact_research_run__pipeline_run=pipeline)
    )
    if target.status == ContactSourceTargetStatus.COMPLETE:
        return False
    target.status = ContactSourceTargetStatus.RUNNING
    target.started_at = target.started_at or timezone.now()
    target.save(update_fields=("status", "started_at"))
    step_key = f"{envelope.idempotency_key}:effect"
    active_fetcher = fetcher or SafeHttpFetcher(settings.RUNTIME_SETTINGS.fetch)
    try:
        result = active_fetcher.fetch(target.requested_url)
        artifact = _persist_contact_artifact(target, result)
        encoding = result.encoding if result.encoding else "utf-8"
        try:
            text = result.body.decode(encoding, errors="replace")
        except LookupError:
            text = result.body.decode("utf-8", errors="replace")
        role = target.contact_research_run.buyer_role_result.roles.order_by("priority").first()
        if role is None:
            raise ContactValidationError("The contact scan has no buyer-role category.")
        extracted: list[ContactRouteItemV2] = []
        source_id = target.research_source.public_id
        retrieved_at = artifact.retrieved_at
        for ordinal, (route_type, value, exact, start, end) in enumerate(
            _candidate_routes(text, result.final_url), start=1
        ):
            try:
                normalized = _normalize_route_value(route_type, value)
            except ContactValidationError:
                continue
            evidence = _evidence(
                artifact,
                ordinal=ordinal,
                kind=route_type,
                exact=exact,
                normalized=normalized,
                start=start,
                end=end,
            )
            item = ContactRouteItemV2(
                route_type=route_type,  # type: ignore[arg-type]
                route_origin="public_source",
                value=value,
                contact_person_id=None,
                buyer_role_key=role.role_key,
                observation_status="published_officially",
                freshness_status="current",
                deliverability_status="unknown",
                outreach_eligibility="unreviewed",
                source_ids=(source_id,),
                evidence_ids=(evidence.public_id,),
                retrieved_at=retrieved_at.isoformat(),
                confidence=0.99,
            )
            extracted.append(item)
            _store_route(
                company=target.contact_research_run.opportunity.company,
                buyer_role=role,
                route_type=item.route_type,
                route_origin=RouteOrigin.PUBLIC_SOURCE,
                value=item.value,
                confidence=item.confidence,
                observation_status=item.observation_status,
                freshness_status=item.freshness_status,
                research_source=target.research_source,
                evidence=evidence,
                source_ids=list(item.source_ids),
                evidence_ids=list(item.evidence_ids),
                actor=None,
                provenance_note="Literal route extracted from a registered official source.",
                retrieved_at=retrieved_at,
            )
        ContactRouteResultV2(
            schema_version="2.1",
            prompt_version="2.1.0",
            routes=tuple(extracted),
            unknowns=(() if extracted else ("No literal public contact route was present.",)),
            review_flags=(),
        )
        target.status = ContactSourceTargetStatus.COMPLETE
        target.route_count = len(extracted)
        target.completed_at = timezone.now()
        target.error_code = ""
        target.safe_error_message = ""
        target.save(
            update_fields=(
                "status",
                "route_count",
                "completed_at",
                "error_code",
                "safe_error_message",
            )
        )
        PipelineStepRun.objects.create(
            pipeline_run=pipeline,
            stage=f"contact_source:{target.pk}",
            status=StepStatus.COMPLETE,
            idempotency_key=step_key,
            started_at=target.started_at,
            completed_at=target.completed_at,
            input_ids={"research_source_id": str(target.research_source_id)},
            output_ids={"artifact_id": str(artifact.pk), "route_count": len(extracted)},
        )
    except (SafeFetchError, ContactValidationError, ContactConfigurationError) as exc:
        target.status = ContactSourceTargetStatus.FAILED
        target.error_code = getattr(exc, "code", "CONTACT_SCAN_FAILED")[:64]
        target.safe_error_message = _safe_message(exc)
        target.completed_at = timezone.now()
        target.save(update_fields=("status", "error_code", "safe_error_message", "completed_at"))
        PipelineStepRun.objects.create(
            pipeline_run=pipeline,
            stage=f"contact_source:{target.pk}",
            status=StepStatus.FAILED,
            idempotency_key=step_key,
            started_at=target.started_at,
            completed_at=target.completed_at,
            input_ids={"research_source_id": str(target.research_source_id)},
            last_error_code=target.error_code,
            last_error_message=target.safe_error_message,
        )
    _settle_contact_run(target.contact_research_run_id)
    return True


@transaction.atomic
def create_human_route(
    *,
    company_id: UUID,
    buyer_role_id: UUID,
    actor: User,
    route_type: str,
    value: str,
    provenance_note: str,
    request_id: UUID | None = None,
) -> ContactRoute:
    _require_permission(actor, "contacts.add_human_route")
    if route_type not in HUMAN_ROUTE_TYPES:
        raise ContactValidationError(
            "Human entry may use only an explicit human-origin route type."
        )
    if len(provenance_note.strip()) < 5:
        raise ContactValidationError("Human-origin routes require a provenance note.")
    company = Company.objects.get(pk=company_id)
    role = BuyerRoleHypothesis.objects.select_related("result__contact_research_run").get(
        pk=buyer_role_id
    )
    if role.result.contact_research_run.opportunity.company_id != company.pk:
        raise ContactValidationError("The buyer role belongs to a different company.")
    if route_type == RouteType.WARM_INTRODUCTION:
        origin = RouteOrigin.HUMAN_ENTERED
    elif route_type == RouteType.EXISTING_RELATIONSHIP:
        origin = RouteOrigin.EXISTING_RELATIONSHIP
    else:
        origin = RouteOrigin.EVENT
    route, _created = _store_route(
        company=company,
        buyer_role=role,
        route_type=route_type,
        route_origin=origin,
        value=value,
        confidence=1.0,
        observation_status="human_confirmed",
        freshness_status="current",
        research_source=None,
        evidence=None,
        source_ids=[],
        evidence_ids=[],
        actor=actor,
        provenance_note=provenance_note.strip(),
        retrieved_at=timezone.now(),
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="contacts.human_route_created",
        object_type="contact_route",
        object_id=route.pk,
        after_summary={"route_type": route.route_type, "route_origin": route.route_origin},
        reason_key="human_route_provenance_recorded",
        request_id=request_id,
    )
    return route


@transaction.atomic
def review_contact_route(
    *,
    route_id: UUID,
    actor: User,
    outreach_eligibility: str,
    legal_review_status: str,
    jurisdiction: str,
    recommendation: str,
    reason: str,
    request_id: UUID | None = None,
) -> ContactRoute:
    _require_permission(actor, "contacts.review_contact_route")
    if outreach_eligibility not in {"eligible_after_human_review", "blocked", "suppressed"}:
        raise ContactValidationError("Unknown outreach eligibility review outcome.")
    if legal_review_status not in {"approved", "blocked", "pending", "not_required"}:
        raise ContactValidationError("Unknown legal review status.")
    if recommendation not in {
        "warm_introduction",
        "existing_relationship",
        "company_contact_form",
        "public_role_inbox",
        "public_individual_business_email",
        "professional_profile_message",
        "event_or_conference_connection",
        "phone",
        "research_more",
        "do_not_contact",
    }:
        raise ContactValidationError("Unknown contact-route recommendation.")
    if len(reason.strip()) < 5:
        raise ContactValidationError("Route review requires an audited reason.")
    route = (
        ContactRoute.objects.select_for_update()
        .select_related("company", "contact_person")
        .get(pk=route_id)
    )
    if _is_suppressed(
        company=route.company,
        route_hmac=route.normalized_hmac,
        person=route.contact_person,
    ):
        outreach_eligibility = "suppressed"
        recommendation = "do_not_contact"
    before = {
        "outreach_eligibility": route.outreach_eligibility,
        "legal_review_status": route.legal_review_status,
        "recommendation": route.recommendation,
    }
    route.outreach_eligibility = outreach_eligibility
    route.legal_review_status = legal_review_status
    route.jurisdiction = jurisdiction.strip().upper()[:2]
    route.recommendation = recommendation
    route.row_version += 1
    route.save(
        update_fields=(
            "outreach_eligibility",
            "legal_review_status",
            "jurisdiction",
            "recommendation",
            "row_version",
            "updated_at",
        )
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="contacts.route_reviewed",
        object_type="contact_route",
        object_id=route.pk,
        before_summary=before,
        after_summary={
            "outreach_eligibility": route.outreach_eligibility,
            "legal_review_status": route.legal_review_status,
            "recommendation": route.recommendation,
        },
        reason_key="human_contact_route_review",
        request_id=request_id,
    )
    return route


@transaction.atomic
def add_suppression(
    *,
    actor: User,
    route_id: UUID,
    reason_type: str,
    reason_note: str,
    request_id: UUID | None = None,
) -> SuppressionEntry:
    _require_permission(actor, "contacts.add_suppression")
    if reason_type not in {"unsubscribe", "objection", "manual", "legal"}:
        raise ContactValidationError("Unknown suppression reason type.")
    route = ContactRoute.objects.select_for_update().get(pk=route_id)
    entry = SuppressionEntry.objects.create(
        company=route.company,
        contact_person=route.contact_person,
        normalized_hmac=route.normalized_hmac,
        scope_type="route",
        reason_type=reason_type,
        reason_note=reason_note.strip()[:1_000],
        created_by=actor,
    )
    ContactRoute.objects.filter(
        company=route.company, normalized_hmac=route.normalized_hmac
    ).update(
        outreach_eligibility="suppressed",
        recommendation="do_not_contact",
        row_version=route.row_version + 1,
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="contacts.route_suppressed",
        object_type="contact_route",
        object_id=route.pk,
        after_summary={"suppression_id": str(entry.pk), "reason_type": reason_type},
        reason_key="synchronous_contact_suppression",
        request_id=request_id,
    )
    return entry


@transaction.atomic
def select_contact_route(
    *,
    opportunity_id: UUID,
    route_id: UUID,
    actor: User,
    contact_purpose: str,
    lawful_basis_note: str,
    retention_policy: str,
    request_id: UUID | None = None,
) -> ContactSelection:
    _require_permission(actor, "contacts.select_contact_route")
    opportunity = Opportunity.objects.get(pk=opportunity_id)
    state = OpportunitySolutionState.objects.select_related("approved_version").get(
        opportunity=opportunity
    )
    route = (
        ContactRoute.objects.select_for_update()
        .select_related("company", "contact_person", "buyer_role__result__solution_version")
        .get(pk=route_id)
    )
    if route.company_id != opportunity.company_id or route.buyer_role is None:
        raise ContactValidationError("The route is not bound to this opportunity and buyer role.")
    buyer_role = route.buyer_role
    if state.status != SolutionStateStatus.APPROVED or state.approved_version_id is None:
        raise ContactValidationError("The opportunity no longer has an approved solution.")
    if buyer_role.result.solution_version_id != state.approved_version_id:
        raise ContactValidationError("The route belongs to a different solution version.")
    if _is_suppressed(
        company=route.company,
        route_hmac=route.normalized_hmac,
        person=route.contact_person,
    ):
        raise ContactValidationError("Suppression blocks target selection.")
    if route.outreach_eligibility != "eligible_after_human_review":
        raise ContactValidationError("The route requires explicit human eligibility review.")
    if route.legal_review_status != "approved":
        raise ContactValidationError("The exact route requires approved legal review.")
    selection = ContactSelection.objects.create(
        opportunity=opportunity,
        solution_version_id=state.approved_version_id,
        buyer_role=buyer_role,
        contact_route=route,
        selected_by=actor,
        contact_purpose=contact_purpose.strip()[:500],
        jurisdiction=route.jurisdiction,
        legal_review_status=route.legal_review_status,
        lawful_basis_note=lawful_basis_note.strip()[:1_000],
        retention_policy=retention_policy.strip()[:100],
        route_row_version=route.row_version,
    )
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="contacts.route_selected",
        object_type="contact_selection",
        object_id=selection.pk,
        after_summary={
            "opportunity_id": str(opportunity.pk),
            "route_id": str(route.pk),
            "route_row_version": route.row_version,
        },
        reason_key="human_exact_target_selection",
        request_id=request_id,
    )
    return selection


@transaction.atomic
def create_human_person_observation(
    *,
    company_id: UUID,
    actor: User,
    professional_name: str,
    role_title: str,
    department: str,
    provenance_note: str,
) -> ContactObservation:
    _require_permission(actor, "contacts.add_human_route")
    if len(provenance_note.strip()) < 5:
        raise ContactValidationError("A human-confirmed person observation requires provenance.")
    company = Company.objects.get(pk=company_id)
    normalized_name = " ".join(professional_name.casefold().split())
    person, _created = ContactPerson.objects.get_or_create(
        normalized_name=normalized_name,
        defaults={"professional_name": professional_name.strip(), "created_by": actor},
    )
    return ContactObservation.objects.create(
        person=person,
        company=company,
        role_title=role_title.strip(),
        department=department.strip(),
        observation_origin="human_confirmed",
        observed_at=timezone.now(),
        freshness_status="current",
        provenance_note=provenance_note.strip(),
        created_by=actor,
    )


@transaction.atomic
def mark_contact_pipeline_failed(*, pipeline_run_id: UUID, error: Exception) -> None:
    pipeline = PipelineRun.objects.select_for_update().filter(pk=pipeline_run_id).first()
    if pipeline is None or pipeline.status in {PipelineStatus.COMPLETE, PipelineStatus.FAILED}:
        return
    safe = _safe_message(error)
    pipeline.status = PipelineStatus.FAILED
    pipeline.stage = "contact_research_failed"
    pipeline.last_error_code = "CONTACT_RESEARCH_FAILED"
    pipeline.last_error_message = safe
    pipeline.completed_at = timezone.now()
    pipeline.save(
        update_fields=(
            "status",
            "stage",
            "last_error_code",
            "last_error_message",
            "completed_at",
            "updated_at",
        )
    )
    ContactResearchRun.objects.filter(pipeline_run=pipeline).update(
        status=ContactResearchStatus.FAILED,
        error_code="CONTACT_RESEARCH_FAILED",
        safe_error_message=safe,
        completed_at=timezone.now(),
    )
