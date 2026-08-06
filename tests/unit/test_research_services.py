import json

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.operations.commands import (
    COMPANIES_AGGREGATE_COMMAND_TYPE,
    RESEARCH_EXTRACT_COMMAND_TYPE,
    RESEARCH_PUBLIC_COMMAND_TYPE,
    SIGNALS_CLASSIFY_COMMAND_TYPE,
)
from apps.operations.models import ProviderCall, ProviderCallStatus, TaskOutbox
from apps.operations.outbox import build_envelope
from apps.opportunities.models import Opportunity, ResearchStatus
from apps.opportunities.services import execute_company_aggregation
from apps.providers.contracts import (
    ProviderSourceV1,
    StructuredResearchResultV2,
    WebResearchResultV2,
)
from apps.research.contracts import ResearchClaimV2, ResearchExtractionV2
from apps.research.models import (
    ResearchClaim,
    ResearchDossier,
    ResearchReportArtifact,
    ResearchRun,
    ResearchRunStatus,
    ResearchSource,
)
from apps.research.services import (
    ResearchRequestError,
    ResearchValidationError,
    execute_public_research,
    execute_research_extraction,
    mark_research_failed,
    request_standard_research,
)
from apps.signals.classification import execute_signal_classification
from apps.signals.services import execute_signal_detection
from tests.unit.test_job_services import ASHBY_FIXTURE, poll_ashby

REPORT = "\n\n".join(
    f"## {heading}\nFixture evidence for this bounded section."
    for heading in (
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
)


def _runtime(*, enabled: bool):
    features = settings.RUNTIME_SETTINGS.features.model_copy(
        update={
            "openai_enabled": enabled,
            "web_search_enabled": enabled,
            "standard_research_enabled": enabled,
        }
    )
    return settings.RUNTIME_SETTINGS.model_copy(update={"features": features})


def _opportunity(user: User, tmp_path: object) -> Opportunity:
    payload = json.loads(ASHBY_FIXTURE.read_text())
    payload["jobs"][0]["descriptionPlain"] = (
        "Design workflow automation and a governed knowledge base. "
        "Own data integration across operating systems."
    )
    poll_ashby(
        user,
        "research-fixture:source",
        json.dumps(payload).encode(),
        tmp_path,
    )
    execute_signal_detection(build_envelope(TaskOutbox.objects.get(command_type="signals.detect")))
    execute_signal_classification(
        build_envelope(TaskOutbox.objects.get(command_type=SIGNALS_CLASSIFY_COMMAND_TYPE))
    )
    execute_company_aggregation(
        build_envelope(TaskOutbox.objects.get(command_type=COMPANIES_AGGREGATE_COMMAND_TYPE))
    )
    return Opportunity.objects.get()


class FixtureResearchProvider:
    def __init__(self, *, invalid_source: bool = False) -> None:
        self.invalid_source = invalid_source
        self.public_request = None
        self.extraction_request = None

    def web_research(self, request, *, policy, pipeline_run):
        self.public_request = request
        ProviderCall.objects.create(
            pipeline_run=pipeline_run,
            provider="openai",
            operation="research.web_search",
            request_sha256="a" * 64,
            model_policy_snapshot=policy.model_dump(mode="json"),
            external_response_id="resp_public_fixture",
            status=ProviderCallStatus.COMPLETE,
            retention_class="research_report_store_false",
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        return WebResearchResultV2(
            report_markdown=REPORT,
            response_id="resp_public_fixture",
            response_model=policy.model_id,
            sources=(
                ProviderSourceV1(
                    url="https://acme.example/about",
                    title="About Acme",
                    source_reference="provider-source-1",
                ),
            ),
            citation_annotations=(
                {
                    "type": "url_citation",
                    "url": "https://acme.example/about",
                    "start_index": 10,
                    "end_index": 20,
                },
            ),
        )

    def research_extraction(self, request, *, policy, pipeline_run):
        self.extraction_request = request
        ProviderCall.objects.create(
            pipeline_run=pipeline_run,
            provider="openai",
            operation="research.extract",
            request_sha256="b" * 64,
            model_policy_snapshot=policy.model_dump(mode="json"),
            external_response_id="resp_extract_fixture",
            status=ProviderCallStatus.COMPLETE,
            retention_class="research_extraction_store_false",
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        source_id = "SRC-999999" if self.invalid_source else "SRC-000001"
        output = ResearchExtractionV2(
            schema_version="2.1",
            prompt_version="2.1.0",
            executive_summary="Public evidence corroborates a current capability initiative.",
            claims=(
                ResearchClaimV2(
                    claim_key="CLM-900001",
                    claim_type="observed_fact",
                    claim_category="signal_context",
                    statement="The public company context corroborates the observed job signal.",
                    source_ids=(source_id,),
                    signal_ids=(request.known_signal_ids[0],),
                    evidence_ids=(request.known_evidence_ids[0],),
                    confidence=0.82,
                    current_as_of=None,
                    expires_at=None,
                    conflict_group=None,
                ),
            ),
            ownership_context_claim_ids=(),
            external_partner_context_claim_ids=(),
            infrastructure_context_claim_ids=(),
            evidence_against_claim_ids=(),
            conflicts=(),
            unknowns=("External-partner openness remains unknown.",),
            review_flags=(),
        )
        return StructuredResearchResultV2(
            output=output,
            response_id="resp_extract_fixture",
            response_model=policy.model_id,
        )


@pytest.mark.django_db
def test_two_pass_research_persists_report_sources_claims_and_dossier(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="research-fixture-user")
    opportunity = _opportunity(user, tmp_path)
    provider = FixtureResearchProvider()

    with override_settings(RUNTIME_SETTINGS=_runtime(enabled=True), MEDIA_ROOT=tmp_path):
        scheduled = request_standard_research(opportunity_id=opportunity.pk, actor=user)
        public_outbox = TaskOutbox.objects.get(command_type=RESEARCH_PUBLIC_COMMAND_TYPE)
        assert execute_public_research(build_envelope(public_outbox), provider=provider)
        extraction_outbox = TaskOutbox.objects.get(command_type=RESEARCH_EXTRACT_COMMAND_TYPE)
        assert execute_research_extraction(build_envelope(extraction_outbox), provider=provider)
        assert (
            execute_research_extraction(build_envelope(extraction_outbox), provider=provider)
            is False
        )

    research_run = ResearchRun.objects.get(pk=scheduled.research_run.pk)
    opportunity.refresh_from_db()
    assert research_run.status == ResearchRunStatus.COMPLETE
    assert opportunity.research_status == ResearchStatus.COMPLETE
    assert opportunity.next_action_key == "solution_design"
    assert ResearchReportArtifact.objects.filter(research_run=research_run).exists()
    assert ResearchSource.objects.get(research_run=research_run).public_id == "SRC-000001"
    claim = ResearchClaim.objects.get(research_run=research_run)
    assert claim.public_id == "CLM-000001"
    assert claim.sources.count() == 1
    assert claim.signals.count() == 1
    assert claim.evidence_items.count() == 1
    assert ResearchDossier.objects.get(research_run=research_run).markdown_sha256
    public_payload = provider.public_request.model_dump(mode="json")
    serialized = json.dumps(public_payload).casefold()
    assert "strategic_fit" not in serialized
    assert '"asset_ids"' not in serialized
    assert '"opportunity_mode"' not in serialized
    assert '"contact_routes"' not in serialized
    assert provider.extraction_request.registered_sources[0].source_id == "SRC-000001"


@pytest.mark.django_db
def test_extraction_rejects_fabricated_source_and_preserves_public_report(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="research-invalid-source")
    opportunity = _opportunity(user, tmp_path)
    provider = FixtureResearchProvider(invalid_source=True)

    with override_settings(RUNTIME_SETTINGS=_runtime(enabled=True), MEDIA_ROOT=tmp_path):
        scheduled = request_standard_research(opportunity_id=opportunity.pk, actor=user)
        public_outbox = TaskOutbox.objects.get(command_type=RESEARCH_PUBLIC_COMMAND_TYPE)
        execute_public_research(build_envelope(public_outbox), provider=provider)
        extraction_outbox = TaskOutbox.objects.get(command_type=RESEARCH_EXTRACT_COMMAND_TYPE)
        with pytest.raises(ResearchValidationError):
            execute_research_extraction(build_envelope(extraction_outbox), provider=provider)
        mark_research_failed(
            pipeline_run_id=scheduled.research_run.pipeline_run_id,
            error=ResearchValidationError("fabricated source"),
            extraction=True,
        )

    scheduled.research_run.refresh_from_db()
    assert scheduled.research_run.status == ResearchRunStatus.PARTIAL
    assert ResearchReportArtifact.objects.filter(research_run=scheduled.research_run).exists()
    assert ResearchClaim.objects.count() == 0


@pytest.mark.django_db
def test_disabled_standard_research_creates_no_run(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="research-disabled")
    opportunity = _opportunity(user, tmp_path)

    with (
        override_settings(RUNTIME_SETTINGS=_runtime(enabled=False)),
        pytest.raises(ResearchRequestError, match="disabled"),
    ):
        request_standard_research(opportunity_id=opportunity.pk, actor=user)

    assert ResearchRun.objects.count() == 0
