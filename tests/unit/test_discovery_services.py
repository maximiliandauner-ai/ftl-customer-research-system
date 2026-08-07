import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.discovery.models import (
    DiscoveryCandidate,
    DiscoveryQuery,
    DiscoveryRunReason,
    DiscoveryStatus,
    EndpointWatch,
    SearchDefinition,
)
from apps.discovery.services import (
    DiscoveryLeaseBusy,
    create_discovery_run,
    execute_discovery,
    render_query,
    schedule_daily_runs,
)
from apps.operations.models import (
    PipelineRun,
    ProviderCall,
    ProviderCallStatus,
    TaskOutbox,
)
from apps.operations.outbox import build_envelope
from apps.providers.contracts import (
    ProviderDiscoveryCandidateV2,
    ProviderDiscoveryOutputV2,
    ProviderSourceV1,
    WebDiscoveryResultV2,
)
from apps.sources.models import (
    CandidateOrigin,
    CandidateStatus,
    ProviderType,
    SourceCandidate,
    SourceEndpoint,
)


def _runtime(*, openai: bool, web: bool):
    features = settings.RUNTIME_SETTINGS.features.model_copy(
        update={"openai_enabled": openai, "web_search_enabled": web}
    )
    return settings.RUNTIME_SETTINGS.model_copy(update={"features": features})


def _known_endpoint(url: str = "https://example.com/jobs") -> SourceEndpoint:
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    candidate = SourceCandidate.objects.create(
        url_original=url,
        url_canonical=url,
        url_sha256=url_hash,
        status=CandidateStatus.REGISTERED,
        idempotency_key=f"fixture:{url_hash}",
    )
    endpoint = SourceEndpoint.objects.create(
        candidate=candidate,
        provider_type=ProviderType.GENERIC_WEB,
        base_url_original=url,
        base_url_canonical=url,
        base_url_sha256=url_hash,
    )
    candidate.registered_endpoint = endpoint
    candidate.save(update_fields=("registered_endpoint",))
    return endpoint


def _manual_run() -> tuple[object, TaskOutbox]:
    definition = SearchDefinition.objects.get(definition_key="ftl-capability-demand", active=True)
    end = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
    command = create_discovery_run(
        definition,
        logical_window_start=end - timedelta(days=definition.lookback_days),
        logical_window_end=end,
        reason=DiscoveryRunReason.MANUAL,
        actor=None,
    )
    return command.run, command.outbox


class FixtureDiscoveryProvider:
    def __init__(self, candidates: tuple[ProviderDiscoveryCandidateV2, ...]) -> None:
        self.candidates = candidates
        self.calls = 0

    def web_discovery(self, request, *, policy, pipeline_run):
        self.calls += 1
        ProviderCall.objects.create(
            pipeline_run=pipeline_run,
            provider="openai",
            operation="discovery.web_search",
            request_sha256="a" * 64,
            model_policy_snapshot=policy.model_dump(mode="json"),
            external_response_id="resp_fixture",
            status=ProviderCallStatus.COMPLETE,
            retention_class="store_false",
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        return WebDiscoveryResultV2(
            output=ProviderDiscoveryOutputV2(
                candidates=self.candidates,
                queries_executed=(request.query,),
            ),
            response_id="resp_fixture",
            response_model=policy.model_id,
            sources=tuple(
                ProviderSourceV1(
                    url=candidate.url,
                    source_reference=candidate.provider_source_reference,
                )
                for candidate in self.candidates
                if candidate.provider_source_reference
            ),
        )


@pytest.mark.django_db
def test_disabled_provider_still_polls_known_endpoint_via_durable_outbox() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    endpoint = _known_endpoint()
    EndpointWatch.objects.create(source_endpoint=endpoint, next_poll_at=timezone.now())
    run, outbox = _manual_run()

    with override_settings(RUNTIME_SETTINGS=_runtime(openai=False, web=False)):
        envelope = build_envelope(outbox)
        execute_discovery(envelope)
        execute_discovery(envelope)

    run.refresh_from_db()
    assert run.status == DiscoveryStatus.COMPLETE
    assert run.known_endpoints_queued == 1
    assert run.warnings == ["web_search_disabled"]
    assert DiscoveryQuery.objects.count() == 0
    assert PipelineRun.objects.filter(pipeline_name="source.ingestion").count() == 1
    assert TaskOutbox.objects.filter(command_type="sources.fetch").count() == 1
    queued = SourceCandidate.objects.get(origin=CandidateOrigin.DISCOVERY)
    assert queued.registered_endpoint == endpoint


@pytest.mark.django_db
def test_structured_provider_candidates_preserve_provenance_and_reject_unsafe_url() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    endpoint = _known_endpoint()
    EndpointWatch.objects.create(source_endpoint=endpoint, next_poll_at=timezone.now())
    run, outbox = _manual_run()
    provider = FixtureDiscoveryProvider(
        (
            ProviderDiscoveryCandidateV2(
                url=endpoint.base_url_canonical,
                title_hint="Public jobs",
                company_hint="Example",
                company_domain_hint="example.com",
                source_type_hint="career_page",
                location_hints=("Berlin",),
                matched_terms=("workflow automation",),
                snippet_hint="Diagnostic result text only",
                candidate_confidence=0.9,
                provider_source_reference="source-1",
            ),
            ProviderDiscoveryCandidateV2(
                url="http://127.0.0.1/private",
                source_type_hint="unknown",
                candidate_confidence=0.1,
                provider_source_reference="source-2",
            ),
        )
    )

    with override_settings(RUNTIME_SETTINGS=_runtime(openai=True, web=True)):
        execute_discovery(build_envelope(outbox), provider=provider)

    run.refresh_from_db()
    assert provider.calls == 1
    assert run.status == DiscoveryStatus.COMPLETE
    assert run.candidates_found == 2
    assert run.duplicate_candidates == 1
    assert run.unsafe_candidates == 1
    assert DiscoveryCandidate.objects.filter(discovery_run=run).count() == 2
    duplicate = SourceCandidate.objects.get(
        idempotency_key__contains="candidate:", status="duplicate"
    )
    assert duplicate.snippet_hint == "Diagnostic result text only"
    unsafe = SourceCandidate.objects.get(status=CandidateStatus.UNSAFE)
    assert unsafe.rejection_reason
    assert unsafe.pipeline_run is None


@pytest.mark.django_db
def test_daily_schedule_is_idempotent_for_one_berlin_window() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    now = datetime(2026, 8, 6, 8, 0, tzinfo=UTC)

    first = schedule_daily_runs(now)
    second = schedule_daily_runs(now)

    assert first == second
    assert len(first) == 2
    assert TaskOutbox.objects.filter(command_type="discovery.execute").count() == 2


@pytest.mark.django_db
def test_creative_learning_query_covers_german_tasks_and_munich_without_company_names() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    definition = SearchDefinition.objects.get(
        definition_key="ftl-creative-learning-demand", active=True
    )

    query = render_query(definition)

    assert definition.countries == ["DE", "AT", "CH"]
    assert '"KI-gestützte Videoproduktion"' in query
    assert '"digitales Lernen"' in query
    assert '"München"' in query
    assert "Werkstudent" in query
    assert "HOFFMANN" not in query
    assert '"DE"' not in query
    assert len(query) <= 2_000


@pytest.mark.django_db
def test_new_discovery_endpoint_becomes_a_watched_source() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    _run, outbox = _manual_run()
    candidate = ProviderDiscoveryCandidateV2(
        url="https://example.org/jobs/creative-ai-learning",
        title_hint="Werkstudent Videoproduktion und KI-Content",
        company_hint="Example Learning GmbH",
        company_domain_hint="example.org",
        source_type_hint="job_posting",
        location_hints=("München",),
        matched_terms=("KI-gestützte Videoproduktion", "digitales Lernen"),
        candidate_confidence=0.95,
        provider_source_reference="source-creative-learning",
    )

    with override_settings(RUNTIME_SETTINGS=_runtime(openai=True, web=True)):
        execute_discovery(
            build_envelope(outbox),
            provider=FixtureDiscoveryProvider((candidate,)),
        )

    endpoint = SourceEndpoint.objects.get(base_url_canonical=candidate.url)
    assert EndpointWatch.objects.filter(source_endpoint=endpoint, active=True).exists()


@pytest.mark.django_db
def test_unexpired_discovery_lease_blocks_duplicate_worker() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    run, outbox = _manual_run()
    run.status = DiscoveryStatus.RUNNING
    run.lease_owner = "celery:first-worker"
    run.lease_expires_at = timezone.now() + timedelta(minutes=5)
    run.save(update_fields=("status", "lease_owner", "lease_expires_at"))

    with pytest.raises(DiscoveryLeaseBusy):
        execute_discovery(
            build_envelope(outbox),
            lease_owner="celery:duplicate-worker",
        )

    run.refresh_from_db()
    assert run.status == DiscoveryStatus.RUNNING
    assert run.lease_owner == "celery:first-worker"
