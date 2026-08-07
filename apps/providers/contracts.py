from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from apps.research.contracts import ResearchExtractionV2

BoundedText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
BoundedUrl = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4_096)]


class ProviderDiscoveryCandidateV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    url: BoundedUrl
    title_hint: BoundedText = ""
    company_hint: BoundedText = ""
    company_domain_hint: BoundedText = ""
    source_type_hint: Literal[
        "personio", "greenhouse", "lever", "ashby", "job_posting", "career_page", "unknown"
    ]
    location_hints: tuple[BoundedText, ...] = Field(default=(), max_length=20)
    matched_terms: tuple[BoundedText, ...] = Field(default=(), max_length=30)
    snippet_hint: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2_000)] = ""
    candidate_confidence: float = Field(ge=0.0, le=1.0)
    provider_source_reference: BoundedText = ""

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        if not value.lower().startswith(("https://", "http://")):
            raise ValueError("Candidate URL must use HTTP or HTTPS.")
        return value


class ProviderDiscoveryOutputV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    prompt_version: Literal["2.2.0"] = "2.2.0"
    candidates: tuple[ProviderDiscoveryCandidateV2, ...] = Field(default=(), max_length=200)
    queries_executed: tuple[BoundedText, ...] = Field(default=(), max_length=20)
    warnings: tuple[BoundedText, ...] = Field(default=(), max_length=50)
    partial: bool = False


class WebDiscoveryRequestV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)]
    language: Annotated[str, StringConstraints(strip_whitespace=True, max_length=16)]
    countries: tuple[Annotated[str, StringConstraints(max_length=2)], ...] = Field(
        default=(), max_length=20
    )
    preferred_domains: tuple[BoundedText, ...] = Field(default=(), max_length=100)
    excluded_domains: tuple[BoundedText, ...] = Field(default=(), max_length=100)
    known_url_hashes: tuple[
        Annotated[str, StringConstraints(min_length=64, max_length=64)], ...
    ] = Field(default=(), max_length=2_000)
    max_candidates: int = Field(ge=1, le=200)
    max_tool_calls: int = Field(ge=1, le=50)
    max_provider_cost_usd: float = Field(gt=0.0, le=100.0)


class ProviderSourceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    url: BoundedUrl
    title: BoundedText = ""
    source_reference: BoundedText = ""


class WebDiscoveryResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    output: ProviderDiscoveryOutputV2
    response_id: BoundedText
    response_model: BoundedText
    sources: tuple[ProviderSourceV1, ...] = Field(default=(), max_length=500)
    usage: dict[str, object] = Field(default_factory=dict)
    tool_calls: tuple[dict[str, object], ...] = Field(default=(), max_length=100)


class WebResearchResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    report_markdown: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    response_id: BoundedText
    response_model: BoundedText
    sources: tuple[ProviderSourceV1, ...] = Field(min_length=1, max_length=500)
    citation_annotations: tuple[dict[str, object], ...] = Field(default=(), max_length=500)
    usage: dict[str, object] = Field(default_factory=dict)
    tool_calls: tuple[dict[str, object], ...] = Field(default=(), max_length=100)


class StructuredResearchResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    output: ResearchExtractionV2
    response_id: BoundedText
    response_model: BoundedText
    usage: dict[str, object] = Field(default_factory=dict)
