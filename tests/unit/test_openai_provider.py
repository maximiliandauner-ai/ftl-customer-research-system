from types import SimpleNamespace
from uuid import UUID

import pytest
from django.core.management import call_command

from apps.operations.models import (
    PipelineRun,
    PipelineStatus,
    PipelineTrigger,
    ProviderCall,
    ProviderCallStatus,
)
from apps.providers.contracts import (
    ProviderDiscoveryCandidateV2,
    ProviderDiscoveryOutputV2,
    WebDiscoveryRequestV2,
)
from apps.providers.openai import OpenAIResponsesProvider, ProviderBudgetBlocked
from apps.providers.policy import ActiveModelPolicyV1, active_model_policy
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


def _pipeline(key: str = "provider-fixture-pipeline") -> PipelineRun:
    return PipelineRun.objects.create(
        pipeline_name="discovery.search",
        stage="discovery",
        status=PipelineStatus.RUNNING,
        trigger=PipelineTrigger.MANUAL,
        idempotency_key=key,
    )


def _policy() -> ActiveModelPolicyV1:
    call_command("bootstrap_ftl_platform", verbosity=0)
    return active_model_policy("discovery.standard_web")


def _request(cost: float = 0.5) -> WebDiscoveryRequestV2:
    return WebDiscoveryRequestV2(
        query='"workflow automation" jobs Germany',
        language="en",
        countries=("DE",),
        max_candidates=10,
        max_tool_calls=4,
        max_provider_cost_usd=cost,
    )


class FixtureResponse:
    id = "resp_123"
    status = "completed"
    model = "gpt-5.6-terra"
    output_parsed = ProviderDiscoveryOutputV2(
        candidates=(
            ProviderDiscoveryCandidateV2(
                url="https://example.com/jobs/1",
                source_type_hint="job_posting",
                candidate_confidence=0.8,
                provider_source_reference="https://example.com/jobs/1",
            ),
        )
    )
    usage = SimpleNamespace(model_dump=lambda **_kwargs: {"input_tokens": 100, "output_tokens": 50})

    def model_dump(self, **_kwargs):
        return {
            "id": self.id,
            "status": self.status,
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [
                            {
                                "url": "https://example.com/jobs/1",
                                "title": "Example role",
                            }
                        ]
                    },
                }
            ],
        }


class FixtureResponses:
    def __init__(self) -> None:
        self.kwargs = None
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        return FixtureResponse()


@pytest.mark.django_db
def test_responses_adapter_uses_current_web_search_and_strict_structured_output() -> None:
    responses = FixtureResponses()
    client = SimpleNamespace(responses=responses)
    provider = OpenAIResponsesProvider(
        api_key="fixture-key",  # pragma: allowlist secret
        client=client,
    )

    result = provider.web_discovery(_request(), policy=_policy(), pipeline_run=_pipeline())

    assert result.response_id == "resp_123"
    assert result.sources[0].url == "https://example.com/jobs/1"
    assert responses.kwargs["tools"] == [{"type": "web_search", "search_context_size": "medium"}]
    assert responses.kwargs["include"] == ["web_search_call.action.sources"]
    assert responses.kwargs["text_format"] is ProviderDiscoveryOutputV2
    assert responses.kwargs["store"] is False
    call = ProviderCall.objects.get()
    assert call.status == ProviderCallStatus.COMPLETE
    assert call.external_response_id == "resp_123"
    assert call.retention_class == "store_false"


@pytest.mark.django_db
def test_provider_budget_block_is_durable_and_happens_before_api_call() -> None:
    responses = FixtureResponses()
    provider = OpenAIResponsesProvider(
        api_key="fixture-key",  # pragma: allowlist secret
        client=SimpleNamespace(responses=responses),
    )

    with pytest.raises(ProviderBudgetBlocked):
        provider.web_discovery(_request(0.6), policy=_policy(), pipeline_run=_pipeline())

    assert responses.calls == 0
    call = ProviderCall.objects.get()
    assert call.status == ProviderCallStatus.FAILED
    assert call.safe_error_code == "OPENAI_BUDGET_BLOCKED"
    assert call.completed_at is not None


def _research_request() -> WebResearchRequestV2:
    return WebResearchRequestV2(
        schema_version="2.1",
        company=PublicCompanyContextV2(
            company_id=UUID("a25c590c-a853-445a-8b1d-ed8ad0f39af6"),
            name="Example GmbH",
            primary_domain="example.com",
            known_official_urls=("https://example.com/",),
        ),
        brief=ResearchBriefV2(
            schema_version="2.1",
            prompt_version="2.1.0",
            objective="Verify public company context.",
            company_identity_note="Example GmbH at example.com.",
            known_observed_facts=(
                BriefFactV2(
                    fact_id="FACT-000001",
                    statement="A public job described workflow automation.",
                    signal_id=UUID("e18ed58c-847e-46a8-af91-729350419773"),
                    evidence_ids=("EV-000001",),
                ),
            ),
            questions=("What current initiative supports the observed need?",),
            disconfirming_questions=("Is the work already fully covered?",),
            required_fact_categories=("company_profile",),
            source_policy=ResearchSourcePolicyV2(
                prefer_first_party=True,
                allowed_domains=("example.com",),
                blocked_domains=(),
                maximum_tool_calls=4,
                maximum_sources=10,
                freshness_window_days=365,
            ),
            explicit_exclusions=("Do not identify people.",),
            unknowns_to_resolve=(),
            stop_conditions=("Stop at the source bound.",),
            review_flags=(),
        ),
        max_tool_calls=4,
        max_sources=10,
        max_provider_cost_usd=1.0,
    )


class ResearchResponse:
    id = "resp_research"
    status = "completed"
    model = "gpt-5.6-terra"
    output_text = "# Executive Summary\nPublic report."
    usage = SimpleNamespace(model_dump=lambda **_kwargs: {"input_tokens": 120})

    def model_dump(self, **_kwargs):
        return {
            "id": self.id,
            "status": self.status,
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [{"url": "https://example.com/about", "title": "About Example"}]
                    },
                },
                {
                    "type": "output_text",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://example.com/about",
                            "start_index": 20,
                            "end_index": 26,
                        }
                    ],
                },
            ],
        }


class ExtractionResponse:
    id = "resp_extract"
    status = "completed"
    model = "gpt-5.6-terra"
    output_parsed = ResearchExtractionV2(
        schema_version="2.1",
        prompt_version="2.1.0",
        executive_summary="A bounded summary.",
        claims=(),
        ownership_context_claim_ids=(),
        external_partner_context_claim_ids=(),
        infrastructure_context_claim_ids=(),
        evidence_against_claim_ids=(),
        conflicts=(),
        unknowns=("Ownership remains unknown.",),
        review_flags=(),
    )
    usage = SimpleNamespace(model_dump=lambda **_kwargs: {"input_tokens": 200})

    def model_dump(self, **_kwargs):
        return {"id": self.id, "status": self.status, "output": []}


class ResearchResponses:
    def __init__(self) -> None:
        self.create_kwargs = None
        self.parse_kwargs = None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return ResearchResponse()

    def parse(self, **kwargs):
        self.parse_kwargs = kwargs
        return ExtractionResponse()


@pytest.mark.django_db
def test_research_adapter_separates_web_report_from_no_web_extraction() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    responses = ResearchResponses()
    provider = OpenAIResponsesProvider(
        api_key="fixture-key",  # pragma: allowlist secret
        client=SimpleNamespace(responses=responses),
    )
    public_run = _pipeline("research-provider-public")
    report = provider.web_research(
        _research_request(),
        policy=active_model_policy("research.standard_web"),
        pipeline_run=public_run,
    )

    assert report.sources[0].url == "https://example.com/about"
    assert responses.create_kwargs["tools"] == [
        {"type": "web_search", "search_context_size": "medium"}
    ]
    assert responses.create_kwargs["include"] == ["web_search_call.action.sources"]
    assert responses.create_kwargs["store"] is False

    extraction_request = ResearchExtractionRequestV2(
        schema_version="2.1",
        research_run_id=UUID("00682954-b6ba-4942-aa9f-7d64474037fd"),
        report_markdown=report.report_markdown,
        registered_sources=(
            RegisteredSourceV2(
                source_id="SRC-000001",
                canonical_url="https://example.com/about",
                title="About Example",
                publisher="example.com",
                retrieved_at="2026-08-06T10:00:00+00:00",
                source_type="official_company",
            ),
        ),
        known_signal_ids=(UUID("e18ed58c-847e-46a8-af91-729350419773"),),
        known_evidence_ids=("EV-000001",),
        max_claims=10,
        stale_after_days=30,
    )
    extraction = provider.research_extraction(
        extraction_request,
        policy=active_model_policy("research.standard_extract"),
        pipeline_run=_pipeline("research-provider-extract"),
    )

    assert extraction.output.schema_version == "2.1"
    assert responses.parse_kwargs["text_format"] is ResearchExtractionV2
    assert "tools" not in responses.parse_kwargs
    assert responses.parse_kwargs["store"] is False
