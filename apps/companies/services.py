from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol, cast
from urllib.parse import urlsplit
from uuid import UUID

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.accounts.models import TeamRole
from apps.companies.contracts import ParsedCompanyFieldV1, ParsedCompanyPageV1
from apps.companies.models import (
    Company,
    CompanyDomain,
    CompanyEnrichmentStatus,
    CompanyFieldObservation,
    CompanyProfileField,
    CompanyProfileRun,
    CompanyProfileSource,
    CompanyProfileSourceKind,
    CompanyStatus,
    CompanyType,
    DomainVerificationStatus,
    EmployeeRange,
)
from apps.companies.profile_parser import parse_company_profile_page
from apps.operations.commands import COMPANY_PROFILE_ENRICH_COMMAND_TYPE
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
from apps.sources.contracts import SafeFetchResultV1
from apps.sources.http import SafeFetchError, SafeHttpFetcher
from apps.sources.policy import canonicalize_url, normalize_company_name
from config.runtime import FetchPolicySettings

PROFILE_PARSER_VERSION = "1.0.2"
PROFILE_REFRESH_AFTER = timedelta(days=30)
MAX_PROFILE_PAGES = 5


class CompanyProfileFetcher(Protocol):
    def fetch(
        self, requested_url: str, *, etag: str = "", last_modified: str = ""
    ) -> SafeFetchResultV1: ...


class RetryableCompanyEnrichmentError(RuntimeError):
    pass


class CompanyEnrichmentError(ValueError):
    pass


@dataclass(frozen=True)
class ScheduledCompanyEnrichment:
    enrichment_run: CompanyProfileRun
    outbox: TaskOutbox
    created: bool


@dataclass(frozen=True)
class EnrichmentStart:
    enrichment_run: CompanyProfileRun
    company: Company
    pipeline_run: PipelineRun
    should_execute: bool


@dataclass(frozen=True)
class ParsedSource:
    source: CompanyProfileSource
    parsed: ParsedCompanyPageV1


def _actor_role_id(user: User | None) -> UUID | None:
    if user is None:
        return None
    return TeamRole.objects.filter(user=user).values_list("pk", flat=True).first()


def _profile_domain(company: Company) -> CompanyDomain | None:
    return (
        company.domains.exclude(verification_status=DomainVerificationStatus.DISPUTED)
        .order_by("-is_primary", "hostname_ascii")
        .first()
    )


@transaction.atomic
def schedule_company_enrichment(
    company: Company,
    *,
    actor: User | None = None,
    trigger: str = PipelineTrigger.SCHEDULED,
    request_id: UUID | None = None,
    logical_date: date | None = None,
) -> ScheduledCompanyEnrichment | None:
    domain = _profile_domain(company)
    if domain is None:
        return None
    window = logical_date or timezone.localdate()
    idempotency_key = (
        f"companies.profile:{company.pk}:{domain.hostname_ascii}:"
        f"{PROFILE_PARSER_VERSION}:{window.isoformat()}"
    )
    existing = CompanyProfileRun.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return ScheduledCompanyEnrichment(
            enrichment_run=existing,
            outbox=existing.pipeline_run.outbox_commands.get(
                idempotency_key=f"{idempotency_key}:execute"
            ),
            created=False,
        )
    root_url = f"https://{domain.hostname_ascii}/"
    now = timezone.now()
    pipeline = PipelineRun.objects.create(
        pipeline_name="companies.profile_enrichment",
        stage="profile_enrichment_queued",
        status=PipelineStatus.QUEUED,
        trigger=trigger,
        requested_by=actor,
        request_id=request_id,
        idempotency_key=idempotency_key,
        object_type="company",
        object_id=company.pk,
        heartbeat_at=now,
        input_count=1,
        policy_versions={
            "company_profile_parser": PROFILE_PARSER_VERSION,
            "fetch_policy": "1.0",
        },
        context={"company_id": str(company.pk), "domain": domain.hostname_ascii},
    )
    enrichment_run = CompanyProfileRun.objects.create(
        company=company,
        pipeline_run=pipeline,
        requested_by=actor,
        status=CompanyEnrichmentStatus.QUEUED,
        parser_version=PROFILE_PARSER_VERSION,
        idempotency_key=idempotency_key,
        source_urls=[root_url],
    )
    payload = TargetCommandPayloadV1(pipeline_run_id=pipeline.pk, object_id=enrichment_run.pk)
    outbox = TaskOutbox(
        command_type=COMPANY_PROFILE_ENRICH_COMMAND_TYPE,
        payload=payload.model_dump(mode="json"),
        payload_schema_version="1.0",
        idempotency_key=f"{idempotency_key}:execute",
        pipeline_run=pipeline,
        request_id=request_id,
    )
    outbox.full_clean()
    outbox.save()
    AuditEvent.objects.create(
        actor_type=ActorType.USER if actor is not None else ActorType.SYSTEM,
        actor_id=_actor_role_id(actor),
        action="companies.profile_enrichment_queued",
        object_type="company",
        object_id=company.pk,
        after_summary={
            "profile_run_id": str(enrichment_run.pk),
            "domain": domain.hostname_ascii,
            "parser_version": PROFILE_PARSER_VERSION,
        },
        reason_key="automated_public_company_profile",
        request_id=request_id,
        pipeline_run=pipeline,
    )
    return ScheduledCompanyEnrichment(enrichment_run, outbox, True)


def schedule_due_company_enrichments(*, limit: int = 100) -> tuple[int, int]:
    bounded_limit = max(1, min(limit, 5_000))
    cutoff = timezone.now() - PROFILE_REFRESH_AFTER
    fresh_current_profile = CompanyProfileRun.objects.filter(
        company_id=OuterRef("pk"),
        parser_version=PROFILE_PARSER_VERSION,
        status__in=(CompanyEnrichmentStatus.COMPLETE, CompanyEnrichmentStatus.PARTIAL),
        completed_at__gte=cutoff,
    )
    companies = (
        Company.objects.filter(
            status__in=(CompanyStatus.ACTIVE, CompanyStatus.PROVISIONAL),
            domains__isnull=False,
        )
        .annotate(has_fresh_current_profile=Exists(fresh_current_profile))
        .filter(has_fresh_current_profile=False)
        .distinct()
        .order_by("created_at", "pk")[:bounded_limit]
    )
    seen = 0
    created = 0
    for company in companies:
        scheduled = schedule_company_enrichment(company)
        seen += 1
        created += int(scheduled is not None and scheduled.created)
    return seen, created


def _validate_envelope(envelope: TaskEnvelopeV2) -> CompanyProfileRun:
    if envelope.command_type != COMPANY_PROFILE_ENRICH_COMMAND_TYPE:
        raise CompanyEnrichmentError("Unsupported company-enrichment command type.")
    enrichment_run = CompanyProfileRun.objects.select_related("pipeline_run", "company").get(
        pk=envelope.object_id,
        pipeline_run_id=envelope.pipeline_run_id,
    )
    outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=enrichment_run.pipeline_run)
    if outbox.idempotency_key != envelope.idempotency_key:
        raise CompanyEnrichmentError("Envelope idempotency does not match the outbox command.")
    return enrichment_run


@transaction.atomic
def _begin_enrichment(envelope: TaskEnvelopeV2, *, recover_started: bool) -> EnrichmentStart:
    enrichment_run = _validate_envelope(envelope)
    enrichment_run = (
        CompanyProfileRun.objects.select_for_update()
        .select_related("pipeline_run", "company")
        .get(pk=enrichment_run.pk)
    )
    pipeline = PipelineRun.objects.select_for_update().get(pk=enrichment_run.pipeline_run_id)
    if enrichment_run.status in {
        CompanyEnrichmentStatus.COMPLETE,
        CompanyEnrichmentStatus.PARTIAL,
    }:
        return EnrichmentStart(enrichment_run, enrichment_run.company, pipeline, False)
    if enrichment_run.status == CompanyEnrichmentStatus.RUNNING and not recover_started:
        return EnrichmentStart(enrichment_run, enrichment_run.company, pipeline, False)
    now = timezone.now()
    attempt = pipeline.attempts + 1
    PipelineStepRun.objects.create(
        pipeline_run=pipeline,
        stage="company_profile_fetch_and_extract",
        status=StepStatus.RUNNING,
        idempotency_key=f"{enrichment_run.idempotency_key}:attempt:{attempt}",
        attempt=attempt,
        started_at=now,
        heartbeat_at=now,
        input_ids={"company_id": str(enrichment_run.company_id)},
    )
    enrichment_run.status = CompanyEnrichmentStatus.RUNNING
    enrichment_run.started_at = enrichment_run.started_at or now
    enrichment_run.error_code = ""
    enrichment_run.safe_error_message = ""
    enrichment_run.save(
        update_fields=(
            "status",
            "started_at",
            "error_code",
            "safe_error_message",
            "updated_at",
        )
    )
    pipeline.status = PipelineStatus.RUNNING
    pipeline.stage = "company_profile_fetch_and_extract"
    pipeline.started_at = pipeline.started_at or now
    pipeline.heartbeat_at = now
    pipeline.attempts = attempt
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
    return EnrichmentStart(enrichment_run, enrichment_run.company, pipeline, True)


def _source_kind(url: str) -> str:
    path = urlsplit(url).path.casefold()
    if path in {"", "/"}:
        return CompanyProfileSourceKind.HOMEPAGE
    if any(term in path for term in ("imprint", "impressum", "legal")):
        return CompanyProfileSourceKind.IMPRINT
    if any(term in path for term in ("about", "ueber", "unternehmen", "team", "studio")):
        return CompanyProfileSourceKind.ABOUT
    return CompanyProfileSourceKind.OTHER


def _persist_source(
    enrichment_run: CompanyProfileRun,
    result: SafeFetchResultV1,
    policy: FetchPolicySettings,
) -> CompanyProfileSource:
    canonical = canonicalize_url(result.final_url, policy)
    storage_key = (
        f"company_profiles/{enrichment_run.company_id}/{enrichment_run.pk}/"
        f"{canonical.sha256[:12]}/"
        f"{result.body_sha256}.bin"
    )
    existing = CompanyProfileSource.objects.filter(
        enrichment_run=enrichment_run,
        canonical_url_sha256=canonical.sha256,
    ).first()
    if existing is not None:
        if (
            existing.body_sha256 != result.body_sha256
            or existing.size_bytes != result.body_size_bytes
        ):
            raise OSError("A retried company-profile URL returned different immutable content.")
        return cast(CompanyProfileSource, existing)
    if default_storage.exists(storage_key):
        if default_storage.size(storage_key) != result.body_size_bytes:
            raise OSError("An immutable company-profile artifact has a different stored size.")
    else:
        stored_key = default_storage.save(storage_key, ContentFile(result.body))
        if stored_key != storage_key:
            raise OSError("Storage did not preserve the immutable company-profile artifact key.")
    return CompanyProfileSource.objects.create(
        enrichment_run=enrichment_run,
        source_kind=_source_kind(result.final_url),
        requested_url=result.requested_url,
        final_url=canonical.canonical,
        canonical_url_sha256=canonical.sha256,
        storage_key=storage_key,
        body_sha256=result.body_sha256,
        size_bytes=result.body_size_bytes,
        content_type=result.content_type,
        encoding=result.encoding,
        retrieved_at=datetime.fromisoformat(result.retrieved_at_iso),
    )


def _identity_core(value: str) -> set[str]:
    ignored = {
        "ag",
        "co",
        "company",
        "corp",
        "gmbh",
        "inc",
        "kg",
        "limited",
        "llc",
        "ltd",
        "studio",
        "the",
        "ug",
    }
    return {
        token.strip(".,&()[]-")
        for token in normalize_company_name(value).split()
        if len(token.strip(".,&()[]-")) >= 3 and token.strip(".,&()[]-") not in ignored
    }


def _identity_matches(company: Company, domain: CompanyDomain, names: set[str]) -> bool:
    expected = _identity_core(company.name) | _identity_core(company.legal_name)
    domain_label = domain.registrable_domain.split(".", 1)[0].replace("-", " ")
    expected |= _identity_core(domain_label)
    if not expected:
        return False
    for candidate in names:
        candidate_tokens = _identity_core(candidate)
        if candidate_tokens and (expected <= candidate_tokens or candidate_tokens <= expected):
            return True
        if expected.intersection(candidate_tokens):
            return True
    return False


def _normalized_field_value(field_name: str, value: str) -> str:
    clean = " ".join(value.split())
    if field_name == CompanyProfileField.HEADQUARTERS_COUNTRY:
        return clean.upper()
    return clean


def _current_field_value(company: Company, field_name: str) -> str:
    return _normalized_field_value(field_name, str(getattr(company, field_name)))


def _unknown_field(company: Company, field_name: str) -> bool:
    value = _current_field_value(company, field_name)
    if field_name == CompanyProfileField.COMPANY_TYPE:
        return value == CompanyType.UNKNOWN
    if field_name == CompanyProfileField.EMPLOYEE_RANGE:
        return value == EmployeeRange.UNKNOWN
    return not value


def _can_apply(company: Company, field_name: str) -> bool:
    if _unknown_field(company, field_name):
        return True
    previous = (
        CompanyFieldObservation.objects.filter(
            enrichment_run__company=company,
            field_name=field_name,
            applied=True,
        )
        .order_by("-created_at")
        .first()
    )
    return previous is not None and _current_field_value(company, field_name) == (
        previous.normalized_value
    )


def _field_rank(source: CompanyProfileSource, field: ParsedCompanyFieldV1) -> tuple[float, int]:
    source_priorities: dict[str, int]
    if field.field_name == "description":
        source_priorities = {
            CompanyProfileSourceKind.ABOUT: 3,
            CompanyProfileSourceKind.HOMEPAGE: 2,
            CompanyProfileSourceKind.OTHER: 1,
            CompanyProfileSourceKind.IMPRINT: 0,
        }
        return float(source_priorities[source.source_kind]), int(field.confidence * 1_000)
    source_priorities = {
        CompanyProfileSourceKind.IMPRINT: 3,
        CompanyProfileSourceKind.ABOUT: 2,
        CompanyProfileSourceKind.HOMEPAGE: 1,
        CompanyProfileSourceKind.OTHER: 0,
    }
    return field.confidence, source_priorities[source.source_kind]


@transaction.atomic
def _complete_enrichment(
    start: EnrichmentStart,
    parsed_sources: list[ParsedSource],
    warnings: list[str],
) -> None:
    enrichment_run = CompanyProfileRun.objects.select_for_update().get(pk=start.enrichment_run.pk)
    company = Company.objects.select_for_update().get(pk=start.company.pk)
    domain = _profile_domain(company)
    if domain is None:
        raise CompanyEnrichmentError("The company no longer has an eligible primary domain.")
    identity_names = {
        name for parsed_source in parsed_sources for name in parsed_source.parsed.identity_names
    }
    if not _identity_matches(company, domain, identity_names):
        raise CompanyEnrichmentError(
            "The official-domain pages did not confirm the expected company identity."
        )
    candidates: dict[str, list[tuple[CompanyProfileSource, ParsedCompanyFieldV1]]] = {}
    for parsed_source in parsed_sources:
        for field in parsed_source.parsed.fields:
            candidates.setdefault(field.field_name, []).append((parsed_source.source, field))
    winners = {
        field_name: max(items, key=lambda item: _field_rank(item[0], item[1]))
        for field_name, items in candidates.items()
    }
    applied_fields: list[str] = []
    for field_name, items in candidates.items():
        winning_source, winning_field = winners[field_name]
        may_apply = _can_apply(company, field_name)
        observed_signatures: set[tuple[UUID, str]] = set()
        for source, field in items:
            normalized = _normalized_field_value(field_name, field.value)
            evidence_hash = hashlib.sha256(field.evidence_excerpt.encode()).hexdigest()
            signature = (source.pk, evidence_hash)
            if signature in observed_signatures:
                continue
            observed_signatures.add(signature)
            is_winner = source.pk == winning_source.pk and field == winning_field
            CompanyFieldObservation.objects.create(
                enrichment_run=enrichment_run,
                source=source,
                field_name=field_name,
                value_text=field.value,
                normalized_value=normalized,
                evidence_excerpt=field.evidence_excerpt,
                evidence_sha256=evidence_hash,
                extraction_method=field.extraction_method,
                confidence=Decimal(str(field.confidence)),
                applied=is_winner and may_apply,
            )
        if may_apply:
            setattr(
                company,
                field_name,
                _normalized_field_value(field_name, winning_field.value),
            )
            applied_fields.append(field_name)
    now = timezone.now()
    status_changed = False
    if (
        company.status == CompanyStatus.PROVISIONAL
        and company.legal_name
        and CompanyProfileField.LEGAL_NAME in winners
    ):
        company.status = CompanyStatus.ACTIVE
        status_changed = True
    if applied_fields or status_changed:
        company.row_version += 1
        company.save(
            update_fields=(
                *sorted(applied_fields),
                *(("status",) if status_changed else ()),
                "row_version",
                "updated_at",
            )
        )
    if company.legal_name and domain.verification_status == DomainVerificationStatus.UNVERIFIED:
        domain.verification_status = DomainVerificationStatus.SOURCE_CONFIRMED
        domain.verification_source_url = parsed_sources[0].source.final_url
        domain.verified_at = now
        domain.last_seen_at = now
        domain.save(
            update_fields=(
                "verification_status",
                "verification_source_url",
                "verified_at",
                "last_seen_at",
                "updated_at",
            )
        )
    known_count = sum(
        not _unknown_field(company, field_name) for field_name in CompanyProfileField.values
    )
    status = (
        CompanyEnrichmentStatus.COMPLETE
        if known_count == len(CompanyProfileField.values)
        else CompanyEnrichmentStatus.PARTIAL
    )
    enrichment_run.status = status
    enrichment_run.source_urls = [item.source.final_url for item in parsed_sources]
    enrichment_run.warnings = warnings[:100]
    enrichment_run.field_count = len(winners)
    enrichment_run.completed_at = now
    enrichment_run.error_code = ""
    enrichment_run.safe_error_message = ""
    enrichment_run.save(
        update_fields=(
            "status",
            "source_urls",
            "warnings",
            "field_count",
            "completed_at",
            "error_code",
            "safe_error_message",
            "updated_at",
        )
    )
    step = PipelineStepRun.objects.select_for_update().get(
        pipeline_run=start.pipeline_run,
        status=StepStatus.RUNNING,
    )
    step.status = StepStatus.COMPLETE
    step.completed_at = now
    step.heartbeat_at = now
    step.output_ids = {
        "profile_run_id": str(enrichment_run.pk),
        "profile_source_ids": [str(item.source.pk) for item in parsed_sources],
        "applied_fields": sorted(applied_fields),
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
    pipeline = PipelineRun.objects.select_for_update().get(pk=start.pipeline_run.pk)
    pipeline.status = PipelineStatus.COMPLETE
    pipeline.stage = "company_profile_enrichment_complete"
    pipeline.completed_at = now
    pipeline.heartbeat_at = now
    pipeline.output_count = len(winners)
    pipeline.warning_count = len(warnings)
    pipeline.last_error_code = ""
    pipeline.last_error_message = ""
    pipeline.row_version += 1
    pipeline.save(
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
        action="companies.profile_enriched",
        object_type="company",
        object_id=company.pk,
        after_summary={
            "profile_run_id": str(enrichment_run.pk),
            "status": status,
            "observed_fields": sorted(winners),
            "applied_fields": sorted(applied_fields),
            "source_count": len(parsed_sources),
        },
        reason_key="source_backed_company_profile",
        request_id=pipeline.request_id,
        pipeline_run=pipeline,
    )


@transaction.atomic
def _record_failure(
    start: EnrichmentStart,
    *,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    enrichment_run = CompanyProfileRun.objects.select_for_update().get(pk=start.enrichment_run.pk)
    pipeline = PipelineRun.objects.select_for_update().get(pk=start.pipeline_run.pk)
    now = timezone.now()
    enrichment_run.status = (
        CompanyEnrichmentStatus.QUEUED if retryable else CompanyEnrichmentStatus.FAILED
    )
    enrichment_run.error_code = code[:64]
    enrichment_run.safe_error_message = message[:500]
    enrichment_run.completed_at = None if retryable else now
    enrichment_run.save(
        update_fields=(
            "status",
            "error_code",
            "safe_error_message",
            "completed_at",
            "updated_at",
        )
    )
    PipelineStepRun.objects.filter(
        pipeline_run=pipeline,
        status=StepStatus.RUNNING,
    ).update(
        status=StepStatus.FAILED,
        completed_at=now,
        heartbeat_at=now,
        last_error_code=code[:64],
        last_error_message=message[:500],
    )
    pipeline.status = PipelineStatus.QUEUED if retryable else PipelineStatus.FAILED
    pipeline.stage = (
        "company_profile_retry_wait" if retryable else "company_profile_enrichment_failed"
    )
    pipeline.completed_at = None if retryable else now
    pipeline.heartbeat_at = now
    pipeline.error_count += 1
    pipeline.last_error_code = code[:64]
    pipeline.last_error_message = message[:500]
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
    if not retryable:
        AuditEvent.objects.create(
            actor_type=ActorType.SYSTEM,
            action="companies.profile_enrichment_failed",
            object_type="company",
            object_id=enrichment_run.company_id,
            after_summary={"profile_run_id": str(enrichment_run.pk), "error_code": code[:64]},
            reason_key="company_profile_failure",
            request_id=pipeline.request_id,
            pipeline_run=pipeline,
        )


def execute_company_enrichment(
    envelope: TaskEnvelopeV2,
    *,
    policy: FetchPolicySettings,
    fetcher: CompanyProfileFetcher | None = None,
    recover_started: bool = False,
) -> None:
    start = _begin_enrichment(envelope, recover_started=recover_started)
    if not start.should_execute:
        return
    active_fetcher = fetcher or SafeHttpFetcher(policy)
    root_url = str(start.enrichment_run.source_urls[0])
    parsed_sources: list[ParsedSource] = []
    warnings: list[str] = []
    try:
        root_result = active_fetcher.fetch(root_url)
        root_source = _persist_source(start.enrichment_run, root_result, policy)
        root_parsed = parse_company_profile_page(
            page_url=root_source.final_url,
            body=root_result.body,
            encoding=root_result.encoding,
        )
        parsed_sources.append(ParsedSource(root_source, root_parsed))
        warnings.extend(root_parsed.warnings)
        urls = list(dict.fromkeys(root_parsed.discovered_urls))[: MAX_PROFILE_PAGES - 1]
        for url in urls:
            try:
                result = active_fetcher.fetch(url)
                source = _persist_source(start.enrichment_run, result, policy)
                parsed = parse_company_profile_page(
                    page_url=source.final_url,
                    body=result.body,
                    encoding=result.encoding,
                )
            except SafeFetchError as exc:
                warnings.append(f"{_source_kind(url)} page unavailable: {exc.code}")
                continue
            parsed_sources.append(ParsedSource(source, parsed))
            warnings.extend(parsed.warnings)
        _complete_enrichment(start, parsed_sources, list(dict.fromkeys(warnings)))
    except SafeFetchError as exc:
        _record_failure(
            start,
            code=exc.code,
            message=exc.safe_message,
            retryable=exc.retryable,
        )
        if exc.retryable:
            raise RetryableCompanyEnrichmentError(exc.safe_message) from exc
    except OSError as exc:
        message = "The company-profile artifact could not be persisted safely."
        _record_failure(start, code="PROFILE_STORAGE_UNAVAILABLE", message=message, retryable=True)
        raise RetryableCompanyEnrichmentError(message) from exc
    except (CompanyEnrichmentError, ValueError) as exc:
        _record_failure(
            start,
            code=(
                "COMPANY_IDENTITY_MISMATCH"
                if "identity" in str(exc).casefold()
                else "PROFILE_EXTRACTION_INVALID"
            ),
            message=str(exc),
            retryable=False,
        )


def mark_company_enrichment_exhausted(*, pipeline_run_id: UUID) -> None:
    enrichment_run = CompanyProfileRun.objects.select_related("company", "pipeline_run").get(
        pipeline_run_id=pipeline_run_id
    )
    if enrichment_run.status != CompanyEnrichmentStatus.QUEUED:
        return
    _record_failure(
        EnrichmentStart(enrichment_run, enrichment_run.company, enrichment_run.pipeline_run, True),
        code="PROFILE_RETRIES_EXHAUSTED",
        message="The official company pages remained unavailable after bounded retries.",
        retryable=False,
    )
