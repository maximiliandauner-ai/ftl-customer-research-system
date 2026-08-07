from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.discovery.contracts import DiscoveryRunRequestV2, SearchDefinitionInputV2
from apps.discovery.models import (
    DiscoveryCandidate,
    DiscoveryQuery,
    DiscoveryRun,
    DiscoveryRunReason,
    DiscoveryStatus,
    EndpointWatch,
    QueryStatus,
    SearchDefinition,
)
from apps.operations.commands import DISCOVERY_EXECUTE_COMMAND_TYPE
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
from apps.providers.contracts import WebDiscoveryRequestV2
from apps.providers.openai import (
    OpenAIResponsesProvider,
    ProviderError,
    ProviderPolicyBlocked,
    ProviderSchemaInvalid,
    WebDiscoveryProvider,
)
from apps.providers.policy import active_model_policy
from apps.sources.contracts import SubmitPublicSourceV1
from apps.sources.models import (
    CandidateOrigin,
    CandidateStatus,
    EndpointStatus,
    SourceCandidate,
    SourceEndpoint,
)
from apps.sources.policy import SourcePolicyError, canonicalize_url, normalize_hostname
from apps.sources.services import queue_registered_endpoint, submit_public_source

BERLIN = ZoneInfo("Europe/Berlin")
DISCOVERY_POLICY_VERSION = "2.2.0"
DEFAULT_MODEL_POLICY_KEY = "discovery.standard_web"
DISCOVERY_LEASE_DURATION = timedelta(minutes=5)


class DiscoveryLeaseBusy(RuntimeError):
    pass


@dataclass(frozen=True)
class DiscoveryRunCommand:
    run: DiscoveryRun
    outbox: TaskOutbox
    created: bool


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def create_definition_version(
    command: SearchDefinitionInputV2,
    *,
    actor: User | None,
) -> SearchDefinition:
    payload = command.model_dump(mode="json")
    payload_hash = _canonical_hash(payload)
    with transaction.atomic():
        previous = (
            SearchDefinition.objects.select_for_update()
            .filter(definition_key=command.definition_key)
            .order_by("-version")
            .first()
        )
        if previous is not None and previous.payload_sha256 == payload_hash:
            return previous
        version = (previous.version + 1) if previous is not None else 1
        SearchDefinition.objects.filter(
            definition_key=command.definition_key,
            active=True,
        ).update(active=False)
        definition = SearchDefinition.objects.create(
            definition_key=command.definition_key,
            version=version,
            name=command.name,
            description=command.description,
            query_template=command.query_template,
            language=command.language,
            countries=list(command.countries),
            locations=list(command.locations),
            capability_clusters=list(command.capability_clusters),
            positive_terms=list(command.positive_terms),
            negative_terms=list(command.negative_terms),
            preferred_domains=list(command.preferred_domains),
            excluded_domains=list(command.excluded_domains),
            source_type_filters=list(command.source_type_filters),
            schedule_key=command.schedule_key,
            active=True,
            max_candidates=command.max_candidates,
            lookback_days=command.lookback_days,
            payload_sha256=payload_hash,
            created_by=actor,
        )
        AuditEvent.objects.create(
            actor_type=ActorType.USER if actor is not None else ActorType.SYSTEM,
            action="discovery.definition_version_created",
            object_type="search_definition",
            object_id=definition.pk,
            after_summary={
                "definition_key": definition.definition_key,
                "version": definition.version,
                "payload_sha256": definition.payload_sha256,
            },
            reason_key="versioned_search_policy",
        )
        return definition


def create_discovery_run(
    definition: SearchDefinition,
    *,
    logical_window_start: datetime,
    logical_window_end: datetime,
    reason: str,
    actor: User | None,
    request: DiscoveryRunRequestV2 | None = None,
) -> DiscoveryRunCommand:
    if logical_window_start.tzinfo is None or logical_window_end.tzinfo is None:
        raise ValueError("Discovery windows must be timezone-aware.")
    if logical_window_end <= logical_window_start:
        raise ValueError("Discovery window end must be after its start.")
    bounds = request or DiscoveryRunRequestV2()
    key_basis = (
        f"{definition.pk}:{logical_window_start.astimezone(UTC).isoformat()}:"
        f"{logical_window_end.astimezone(UTC).isoformat()}:{reason}"
    )
    idempotency_key = f"discovery.window:{_canonical_hash(key_basis)}"
    with transaction.atomic():
        existing = (
            DiscoveryRun.objects.select_related("pipeline_run")
            .filter(idempotency_key=idempotency_key)
            .first()
        )
        if existing is not None:
            return DiscoveryRunCommand(
                existing,
                TaskOutbox.objects.get(pipeline_run=existing.pipeline_run),
                False,
            )
        trigger = (
            PipelineTrigger.SCHEDULED
            if reason == DiscoveryRunReason.SCHEDULED
            else PipelineTrigger.MANUAL
        )
        pipeline = PipelineRun.objects.create(
            pipeline_name="discovery.search",
            stage="discovery_queued",
            status=PipelineStatus.QUEUED,
            trigger=trigger,
            requested_by=actor,
            idempotency_key=f"pipeline:{idempotency_key}",
            object_type="discovery_run",
            heartbeat_at=timezone.now(),
            input_count=1,
            estimated_cost_usd=Decimal(str(bounds.max_provider_cost_usd)),
            policy_versions={
                "discovery": DISCOVERY_POLICY_VERSION,
                "search_definition": f"{definition.definition_key}:{definition.version}",
            },
            context={
                "definition_id": str(definition.pk),
                "logical_window_start": logical_window_start.astimezone(UTC).isoformat(),
                "logical_window_end": logical_window_end.astimezone(UTC).isoformat(),
            },
        )
        run = DiscoveryRun.objects.create(
            definition=definition,
            pipeline_run=pipeline,
            logical_window_start=logical_window_start,
            logical_window_end=logical_window_end,
            run_reason=reason,
            idempotency_key=idempotency_key,
            max_tool_calls=bounds.max_tool_calls,
            max_candidates=definition.max_candidates,
            max_provider_cost_usd=Decimal(str(bounds.max_provider_cost_usd)),
        )
        pipeline.object_id = run.pk
        pipeline.save(update_fields=("object_id", "updated_at"))
        payload = TargetCommandPayloadV1(pipeline_run_id=pipeline.pk, object_id=run.pk)
        outbox = TaskOutbox(
            command_type=DISCOVERY_EXECUTE_COMMAND_TYPE,
            payload=payload.model_dump(mode="json"),
            payload_schema_version="2.0",
            idempotency_key=f"discovery.execute:{run.pk}:{DISCOVERY_POLICY_VERSION}",
            pipeline_run=pipeline,
        )
        outbox.full_clean()
        outbox.save()
        AuditEvent.objects.create(
            actor_type=ActorType.USER if actor is not None else ActorType.SYSTEM,
            action="discovery.run_queued",
            object_type="discovery_run",
            object_id=run.pk,
            after_summary={
                "definition_id": str(definition.pk),
                "definition_version": definition.version,
                "outbox_id": str(outbox.pk),
            },
            reason_key=reason,
            pipeline_run=pipeline,
        )
        return DiscoveryRunCommand(run, outbox, True)


def render_query(definition: SearchDefinition) -> str:
    role_terms = (
        'job OR jobs OR career OR careers OR hiring OR "open position" '
        "OR Stelle OR Stellenangebot OR Karriere OR Werkstudent OR Teilzeit "
        "OR freelance OR contractor"
    )
    capability_terms = " OR ".join(f'"{term}"' for term in definition.positive_terms)
    location_terms = " OR ".join(f'"{item}"' for item in definition.locations)
    query = definition.query_template
    query = query.replace("{{role_terms}}", role_terms)
    query = query.replace("{{capability_terms}}", capability_terms)
    query = query.replace("{{location_terms}}", location_terms)
    for term in definition.negative_terms:
        query += f' -"{term}"'
    return " ".join(query.split())[:2_000]


def previous_berlin_day(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = (now or timezone.now()).astimezone(BERLIN)
    end_local = datetime.combine(current.date(), datetime.min.time(), tzinfo=BERLIN)
    start_local = end_local - timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def schedule_daily_runs(now: datetime | None = None) -> tuple[UUID, ...]:
    window_start, window_end = previous_berlin_day(now)
    run_ids: list[UUID] = []
    for definition in SearchDefinition.objects.filter(
        active=True,
        schedule_key="daily_morning",
    ):
        command = create_discovery_run(
            definition,
            logical_window_start=window_start,
            logical_window_end=window_end,
            reason=DiscoveryRunReason.SCHEDULED,
            actor=None,
        )
        run_ids.append(command.run.pk)
    return tuple(run_ids)


def _begin_execution(
    envelope: TaskEnvelopeV2,
    *,
    lease_owner: str,
) -> tuple[DiscoveryRun, PipelineRun, bool]:
    if envelope.command_type != DISCOVERY_EXECUTE_COMMAND_TYPE:
        raise ValueError("Unsupported discovery command type.")
    with transaction.atomic():
        pipeline = PipelineRun.objects.select_for_update().get(pk=envelope.pipeline_run_id)
        run = DiscoveryRun.objects.select_for_update().get(
            pk=envelope.object_id,
            pipeline_run=pipeline,
        )
        outbox = TaskOutbox.objects.get(pk=envelope.outbox_id, pipeline_run=pipeline)
        if outbox.idempotency_key != envelope.idempotency_key:
            raise ValueError("Envelope idempotency does not match discovery command.")
        if run.status in (
            DiscoveryStatus.COMPLETE,
            DiscoveryStatus.PARTIAL,
            DiscoveryStatus.FAILED,
            DiscoveryStatus.CANCELED,
        ):
            return run, pipeline, False
        now = timezone.now()
        if (
            run.status == DiscoveryStatus.RUNNING
            and run.lease_expires_at is not None
            and run.lease_expires_at > now
        ):
            raise DiscoveryLeaseBusy("Another worker holds the active discovery lease.")
        run.status = DiscoveryStatus.RUNNING
        run.started_at = run.started_at or now
        run.error_code = ""
        run.safe_error_message = ""
        run.lease_owner = lease_owner[:128]
        run.lease_expires_at = now + DISCOVERY_LEASE_DURATION
        run.save(
            update_fields=(
                "status",
                "started_at",
                "error_code",
                "safe_error_message",
                "lease_owner",
                "lease_expires_at",
                "updated_at",
            )
        )
        step, created = PipelineStepRun.objects.get_or_create(
            idempotency_key=f"discovery.execute:{run.pk}:effect",
            defaults={
                "pipeline_run": pipeline,
                "stage": "discovery",
                "status": StepStatus.RUNNING,
                "attempt": pipeline.attempts + 1,
                "started_at": now,
                "heartbeat_at": now,
                "input_ids": {"discovery_run_id": str(run.pk)},
            },
        )
        if not created:
            step.status = StepStatus.RUNNING
            step.attempt = pipeline.attempts + 1
            step.started_at = now
            step.completed_at = None
            step.heartbeat_at = now
            step.last_error_code = ""
            step.last_error_message = ""
            step.save(
                update_fields=(
                    "status",
                    "attempt",
                    "started_at",
                    "completed_at",
                    "heartbeat_at",
                    "last_error_code",
                    "last_error_message",
                    "updated_at",
                )
            )
        pipeline.status = PipelineStatus.RUNNING
        pipeline.stage = "discovery"
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
        return run, pipeline, True


def _hostname_excluded(hostname: str, definition: SearchDefinition) -> bool:
    lowered = hostname.casefold().rstrip(".")
    return any(
        lowered == blocked.casefold().rstrip(".")
        or lowered.endswith(f".{blocked.casefold().rstrip('.')}")
        for blocked in definition.excluded_domains
    )


def _queue_known_endpoints(run: DiscoveryRun) -> int:
    definition = run.definition
    now = timezone.now()
    filters = Q(active=True, source_endpoint__status=EndpointStatus.ACTIVE)
    if run.run_reason == DiscoveryRunReason.SCHEDULED:
        filters &= Q(next_poll_at__lte=run.logical_window_end)
    queued = 0
    with transaction.atomic():
        watch_query = EndpointWatch.objects.select_related("source_endpoint").filter(filters)
        if connection.features.has_select_for_update_skip_locked:
            watch_query = watch_query.select_for_update(skip_locked=True)
        else:
            watch_query = watch_query.select_for_update()
        watches = list(watch_query.order_by("next_poll_at")[:500])
        for watch in watches:
            endpoint = watch.source_endpoint
            hostname = urlparse(endpoint.base_url_canonical).hostname or ""
            if _hostname_excluded(hostname, definition):
                continue
            result = queue_registered_endpoint(
                endpoint=endpoint,
                idempotency_key=f"discovery:{run.pk}:endpoint:{endpoint.pk}",
                trigger=(
                    PipelineTrigger.SCHEDULED
                    if run.run_reason == DiscoveryRunReason.SCHEDULED
                    else PipelineTrigger.MANUAL
                ),
                actor=run.pipeline_run.requested_by,
            )
            queued += int(result.created)
            watch.last_queued_at = now
            watch.next_poll_at = now + timedelta(hours=watch.poll_interval_hours)
            watch.lease_owner = ""
            watch.lease_expires_at = None
            watch.save(
                update_fields=(
                    "last_queued_at",
                    "next_poll_at",
                    "lease_owner",
                    "lease_expires_at",
                    "updated_at",
                )
            )
    return queued


def _is_first_party(candidate_source_type: str, url: str, company_domain: str) -> bool:
    if candidate_source_type in {"personio", "greenhouse", "lever", "ashby"}:
        return True
    hostname = urlparse(url).hostname or ""
    if not company_domain:
        return False
    try:
        hostname_ascii, _unicode = normalize_hostname(hostname)
        company_ascii, _company_unicode = normalize_hostname(company_domain)
    except SourcePolicyError:
        return False
    return hostname_ascii == company_ascii or hostname_ascii.endswith(f".{company_ascii}")


def _register_provider_candidates(
    run: DiscoveryRun,
    query: DiscoveryQuery,
    result: object,
) -> tuple[int, int, int, int, int]:
    from apps.providers.contracts import WebDiscoveryResultV2

    provider_result = WebDiscoveryResultV2.model_validate(result)
    allowed_source_references = {
        reference
        for source in provider_result.sources
        for reference in (source.url, source.source_reference)
        if reference
    }
    invalid_references = sorted(
        {
            candidate.provider_source_reference
            for candidate in provider_result.output.candidates
            if candidate.provider_source_reference
            and candidate.provider_source_reference not in allowed_source_references
        }
    )
    if invalid_references:
        raise ProviderSchemaInvalid(
            "The provider returned candidate references outside its source catalog."
        )
    found = accepted = unsafe = duplicates = first_party_count = 0
    for candidate in provider_result.output.candidates[: run.max_candidates]:
        try:
            canonical = canonicalize_url(candidate.url, settings.RUNTIME_SETTINGS.fetch)
        except SourcePolicyError:
            canonical = None
        if canonical is not None:
            hostname = urlparse(canonical.canonical).hostname or ""
            if _hostname_excluded(hostname, run.definition):
                continue
        candidate_key = f"discovery:{run.pk}:candidate:{_canonical_hash(candidate.url)}"
        existing_endpoint = (
            SourceEndpoint.objects.filter(base_url_sha256=canonical.sha256).first()
            if canonical is not None
            else None
        )
        if existing_endpoint is not None:
            assert canonical is not None
            source_candidate, _created = SourceCandidate.objects.get_or_create(
                idempotency_key=candidate_key,
                defaults={
                    "origin": CandidateOrigin.DISCOVERY,
                    "url_original": canonical.original_redacted,
                    "url_canonical": canonical.canonical,
                    "url_sha256": canonical.sha256,
                    "company_name_hint": candidate.company_hint,
                    "company_domain_hint": candidate.company_domain_hint,
                    "title_hint": candidate.title_hint,
                    "snippet_hint": candidate.snippet_hint,
                    "source_type_hint": candidate.source_type_hint,
                    "matched_terms": list(candidate.matched_terms),
                    "candidate_confidence": Decimal(str(candidate.candidate_confidence)),
                    "status": CandidateStatus.DUPLICATE,
                    "registered_endpoint": existing_endpoint,
                    "submitted_by": run.pipeline_run.requested_by,
                },
            )
            duplicates += 1
        else:
            submission = submit_public_source(
                command=SubmitPublicSourceV1(
                    requested_url=candidate.url,
                    company_name=candidate.company_hint or None,
                    company_domain=candidate.company_domain_hint or None,
                    idempotency_key=candidate_key,
                    public_source_confirmed=True,
                ),
                actor=run.pipeline_run.requested_by,
                policy=settings.RUNTIME_SETTINGS.fetch,
                origin=CandidateOrigin.DISCOVERY,
                trigger=(
                    PipelineTrigger.SCHEDULED
                    if run.run_reason == DiscoveryRunReason.SCHEDULED
                    else PipelineTrigger.MANUAL
                ),
            )
            source_candidate = submission.candidate
            source_candidate.title_hint = candidate.title_hint
            source_candidate.snippet_hint = candidate.snippet_hint
            source_candidate.source_type_hint = candidate.source_type_hint
            source_candidate.matched_terms = list(candidate.matched_terms)
            source_candidate.candidate_confidence = Decimal(str(candidate.candidate_confidence))
            source_candidate.save(
                update_fields=(
                    "title_hint",
                    "snippet_hint",
                    "source_type_hint",
                    "matched_terms",
                    "candidate_confidence",
                )
            )
            accepted += int(submission.accepted)
            unsafe += int(source_candidate.status == CandidateStatus.UNSAFE)
        first_party = _is_first_party(
            candidate.source_type_hint,
            candidate.url,
            candidate.company_domain_hint,
        )
        _provenance, created = DiscoveryCandidate.objects.get_or_create(
            discovery_run=run,
            url_sha256=source_candidate.url_sha256 or _canonical_hash(candidate.url),
            defaults={
                "discovery_query": query,
                "source_candidate": source_candidate,
                "provider_source_reference": candidate.provider_source_reference,
                "location_hints": list(candidate.location_hints),
                "first_party": first_party,
            },
        )
        if created:
            found += 1
            first_party_count += int(first_party)
        registered_endpoint = source_candidate.registered_endpoint
        if registered_endpoint is not None and registered_endpoint.status == EndpointStatus.ACTIVE:
            EndpointWatch.objects.get_or_create(
                source_endpoint=registered_endpoint,
                defaults={"next_poll_at": timezone.now()},
            )
    return found, accepted, unsafe, duplicates, first_party_count


def _provider_for_runtime() -> WebDiscoveryProvider:
    api_key = settings.RUNTIME_SETTINGS.openai_api_key
    if api_key is None:
        raise ProviderError("The OpenAI API credential is not configured.")
    return OpenAIResponsesProvider(api_key=api_key.get_secret_value())


def _run_web_discovery(
    run: DiscoveryRun,
    provider: WebDiscoveryProvider | None,
) -> tuple[int, int, int, int, int, bool, list[str]]:
    if not (
        settings.RUNTIME_SETTINGS.features.openai_enabled
        and settings.RUNTIME_SETTINGS.features.web_search_enabled
    ):
        return 0, 0, 0, 0, 0, False, ["web_search_disabled"]
    query_text = render_query(run.definition)
    query = DiscoveryQuery.objects.create(
        discovery_run=run,
        ordinal=1,
        query_text=query_text,
        query_sha256=_canonical_hash(query_text),
        status=QueryStatus.QUEUED,
    )
    try:
        policy = active_model_policy(DEFAULT_MODEL_POLICY_KEY)
        active_provider = provider or _provider_for_runtime()
        known_hashes = tuple(
            SourceEndpoint.objects.values_list("base_url_sha256", flat=True)[:2_000]
        )
        result = active_provider.web_discovery(
            WebDiscoveryRequestV2(
                query=query_text,
                language=run.definition.language,
                countries=tuple(run.definition.countries),
                preferred_domains=tuple(run.definition.preferred_domains),
                excluded_domains=tuple(run.definition.excluded_domains),
                known_url_hashes=known_hashes,
                max_candidates=run.max_candidates,
                max_tool_calls=run.max_tool_calls,
                max_provider_cost_usd=float(run.max_provider_cost_usd),
            ),
            policy=policy,
            pipeline_run=run.pipeline_run,
        )
        call = ProviderCall.objects.get(
            pipeline_run=run.pipeline_run,
            external_response_id=result.response_id,
        )
        found, accepted, unsafe, duplicates, first_party = _register_provider_candidates(
            run,
            query,
            result,
        )
        query.status = QueryStatus.COMPLETE
        query.provider_call = call
        query.candidate_count = found
        query.completed_at = timezone.now()
        query.save(
            update_fields=(
                "status",
                "provider_call",
                "candidate_count",
                "completed_at",
            )
        )
        return (
            found,
            accepted,
            unsafe,
            duplicates,
            first_party,
            result.output.partial,
            list(result.output.warnings),
        )
    except ObjectDoesNotExist:
        provider_error = ProviderPolicyBlocked(
            "No active model policy is configured for discovery."
        )
        query.status = QueryStatus.FAILED
        query.error_code = provider_error.code
        query.safe_error_message = str(provider_error)
        query.completed_at = timezone.now()
        query.save(
            update_fields=(
                "status",
                "error_code",
                "safe_error_message",
                "completed_at",
            )
        )
        return 0, 0, 0, 0, 0, True, [provider_error.code]
    except ProviderError as exc:
        query.status = QueryStatus.FAILED
        query.error_code = exc.code
        query.safe_error_message = str(exc)[:500]
        query.completed_at = timezone.now()
        query.provider_call = (
            ProviderCall.objects.filter(pipeline_run=run.pipeline_run)
            .order_by("-created_at")
            .first()
        )
        query.save(
            update_fields=(
                "status",
                "error_code",
                "safe_error_message",
                "completed_at",
                "provider_call",
            )
        )
        return 0, 0, 0, 0, 0, True, [exc.code]


def _fail_execution(run: DiscoveryRun, pipeline: PipelineRun, error: Exception) -> None:
    now = timezone.now()
    error_code = "DISCOVERY_EXECUTION_FAILED"
    safe_message = (str(error).replace("\n", " ").strip() or error.__class__.__name__)[:500]
    with transaction.atomic():
        locked = DiscoveryRun.objects.select_for_update().get(pk=run.pk)
        locked.status = DiscoveryStatus.FAILED
        locked.error_code = error_code
        locked.safe_error_message = safe_message
        locked.lease_owner = ""
        locked.lease_expires_at = None
        locked.completed_at = now
        locked.save(
            update_fields=(
                "status",
                "error_code",
                "safe_error_message",
                "lease_owner",
                "lease_expires_at",
                "completed_at",
                "updated_at",
            )
        )
        PipelineStepRun.objects.filter(idempotency_key=f"discovery.execute:{run.pk}:effect").update(
            status=StepStatus.FAILED,
            completed_at=now,
            heartbeat_at=now,
            last_error_code=error_code,
            last_error_message=safe_message,
        )
        locked_pipeline = PipelineRun.objects.select_for_update().get(pk=pipeline.pk)
        locked_pipeline.status = PipelineStatus.FAILED
        locked_pipeline.stage = "discovery_failed"
        locked_pipeline.completed_at = now
        locked_pipeline.heartbeat_at = now
        locked_pipeline.error_count += 1
        locked_pipeline.last_error_code = error_code
        locked_pipeline.last_error_message = safe_message
        locked_pipeline.row_version += 1
        locked_pipeline.save(
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
            action="discovery.run_failed",
            object_type="discovery_run",
            object_id=run.pk,
            after_summary={"error_code": error_code},
            reason_key="bounded_discovery_failure",
            pipeline_run=locked_pipeline,
        )


def _complete_execution(
    run: DiscoveryRun,
    pipeline: PipelineRun,
    *,
    known_count: int,
    web_metrics: tuple[int, int, int, int, int],
    partial: bool,
    warnings: list[str],
) -> None:
    found, accepted, unsafe, duplicates, first_party = web_metrics
    now = timezone.now()
    with transaction.atomic():
        locked = DiscoveryRun.objects.select_for_update().get(pk=run.pk)
        locked.status = DiscoveryStatus.PARTIAL if partial else DiscoveryStatus.COMPLETE
        locked.known_endpoints_queued = known_count
        locked.candidates_found = found
        locked.accepted_candidates = accepted
        locked.unsafe_candidates = unsafe
        locked.duplicate_candidates = duplicates
        locked.first_party_candidates = first_party
        locked.warnings = warnings[:100]
        locked.lease_owner = ""
        locked.lease_expires_at = None
        locked.completed_at = now
        locked.save(
            update_fields=(
                "status",
                "known_endpoints_queued",
                "candidates_found",
                "accepted_candidates",
                "unsafe_candidates",
                "duplicate_candidates",
                "first_party_candidates",
                "warnings",
                "lease_owner",
                "lease_expires_at",
                "completed_at",
                "updated_at",
            )
        )
        step = PipelineStepRun.objects.select_for_update().get(
            idempotency_key=f"discovery.execute:{run.pk}:effect"
        )
        step.status = StepStatus.COMPLETE
        step.completed_at = now
        step.heartbeat_at = now
        step.output_ids = {
            "known_endpoints_queued": known_count,
            "discovery_candidate_count": found,
        }
        step.save(
            update_fields=("status", "completed_at", "heartbeat_at", "output_ids", "updated_at")
        )
        pipeline.status = PipelineStatus.COMPLETE
        pipeline.stage = "discovery_complete"
        pipeline.completed_at = now
        pipeline.heartbeat_at = now
        pipeline.output_count = known_count + found
        pipeline.warning_count = len(warnings)
        pipeline.row_version += 1
        pipeline.save(
            update_fields=(
                "status",
                "stage",
                "completed_at",
                "heartbeat_at",
                "output_count",
                "warning_count",
                "row_version",
                "updated_at",
            )
        )
        AuditEvent.objects.create(
            actor_type=ActorType.SYSTEM,
            action="discovery.run_completed",
            object_type="discovery_run",
            object_id=run.pk,
            after_summary={
                "status": locked.status,
                "known_endpoints_queued": known_count,
                "candidates_found": found,
                "unsafe_candidates": unsafe,
            },
            reason_key="bounded_discovery",
            pipeline_run=pipeline,
        )


def execute_discovery(
    envelope: TaskEnvelopeV2,
    *,
    provider: WebDiscoveryProvider | None = None,
    lease_owner: str | None = None,
) -> None:
    owner = lease_owner or f"service:{uuid4()}"
    run, pipeline, should_execute = _begin_execution(envelope, lease_owner=owner)
    if not should_execute:
        return
    run = DiscoveryRun.objects.select_related("definition", "pipeline_run__requested_by").get(
        pk=run.pk
    )
    try:
        known_count = _queue_known_endpoints(run)
        found, accepted, unsafe, duplicates, first_party, partial, warnings = _run_web_discovery(
            run,
            provider,
        )
        _complete_execution(
            run,
            pipeline,
            known_count=known_count,
            web_metrics=(found, accepted, unsafe, duplicates, first_party),
            partial=partial,
            warnings=warnings,
        )
    except Exception as exc:
        _fail_execution(run, pipeline, exc)
        raise
