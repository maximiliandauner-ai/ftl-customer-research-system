from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

BoundedText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2_000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
EvidenceId = Annotated[str, StringConstraints(pattern=r"^EV-[0-9]{6}$", max_length=9)]
SourceId = Annotated[str, StringConstraints(pattern=r"^SRC-[0-9]{6}$", max_length=10)]
ClaimKey = Annotated[str, StringConstraints(pattern=r"^CLM-[0-9]{6}$", max_length=10)]


class BriefFactV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    fact_id: Annotated[str, StringConstraints(pattern=r"^FACT-[0-9]{6}$", max_length=11)]
    statement: BoundedText
    signal_id: UUID
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=20)


class ResearchSourcePolicyV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    prefer_first_party: bool
    allowed_domains: tuple[ShortText, ...] = Field(max_length=100)
    blocked_domains: tuple[ShortText, ...] = Field(max_length=100)
    maximum_tool_calls: int = Field(ge=1, le=50)
    maximum_sources: int = Field(ge=1, le=100)
    freshness_window_days: int = Field(ge=1, le=3_650)


class ResearchBriefV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.1"]
    prompt_version: Literal["2.1.0"]
    objective: BoundedText
    company_identity_note: BoundedText
    known_observed_facts: tuple[BriefFactV2, ...] = Field(min_length=1, max_length=50)
    questions: tuple[BoundedText, ...] = Field(min_length=1, max_length=12)
    disconfirming_questions: tuple[BoundedText, ...] = Field(min_length=1, max_length=6)
    required_fact_categories: tuple[
        Literal[
            "company_profile",
            "signal_context",
            "current_initiatives",
            "organizational_ownership",
            "external_partner_context",
            "infrastructure_privacy_governance",
            "evidence_against",
        ],
        ...,
    ] = Field(min_length=1, max_length=12)
    source_policy: ResearchSourcePolicyV2
    explicit_exclusions: tuple[BoundedText, ...] = Field(min_length=1, max_length=20)
    unknowns_to_resolve: tuple[BoundedText, ...] = Field(max_length=30)
    stop_conditions: tuple[BoundedText, ...] = Field(min_length=1, max_length=10)
    review_flags: tuple[BoundedText, ...] = Field(max_length=20)


class PublicCompanyContextV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    company_id: UUID
    name: ShortText
    primary_domain: ShortText
    known_official_urls: tuple[Annotated[str, StringConstraints(max_length=4_096)], ...] = Field(
        max_length=30
    )


class WebResearchRequestV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.1"]
    company: PublicCompanyContextV2
    brief: ResearchBriefV2
    max_tool_calls: int = Field(ge=1, le=50)
    max_sources: int = Field(ge=1, le=100)
    max_provider_cost_usd: float = Field(gt=0, le=100)


class RegisteredSourceV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source_id: SourceId
    canonical_url: Annotated[str, StringConstraints(max_length=4_096)]
    title: ShortText
    publisher: ShortText
    retrieved_at: Annotated[str, StringConstraints(max_length=40)]
    source_type: Literal[
        "official_company",
        "official_registry",
        "official_government",
        "reputable_press",
        "public_other",
    ]


class ResearchClaimV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    claim_key: ClaimKey
    claim_type: Literal["observed_fact", "inference", "hypothesis", "unknown"]
    claim_category: Literal[
        "company_profile",
        "signal_context",
        "organizational_ownership",
        "external_partner_context",
        "infrastructure_privacy_governance",
        "evidence_against",
        "other",
    ]
    statement: BoundedText
    source_ids: tuple[SourceId, ...] = Field(max_length=30)
    signal_ids: tuple[UUID, ...] = Field(max_length=30)
    evidence_ids: tuple[EvidenceId, ...] = Field(max_length=50)
    confidence: float = Field(ge=0, le=1)
    current_as_of: date | None
    expires_at: date | None
    conflict_group: ShortText | None


class ResearchConflictV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    conflict_key: ShortText
    claim_keys: tuple[ClaimKey, ...] = Field(min_length=2, max_length=20)
    concise_summary: BoundedText
    source_ids: tuple[SourceId, ...] = Field(min_length=1, max_length=30)


class ResearchExtractionV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.1"]
    prompt_version: Literal["2.1.0"]
    executive_summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4_000)]
    claims: tuple[ResearchClaimV2, ...] = Field(max_length=40)
    ownership_context_claim_ids: tuple[ClaimKey, ...] = Field(max_length=40)
    external_partner_context_claim_ids: tuple[ClaimKey, ...] = Field(max_length=40)
    infrastructure_context_claim_ids: tuple[ClaimKey, ...] = Field(max_length=40)
    evidence_against_claim_ids: tuple[ClaimKey, ...] = Field(max_length=40)
    conflicts: tuple[ResearchConflictV2, ...] = Field(max_length=20)
    unknowns: tuple[BoundedText, ...] = Field(max_length=40)
    review_flags: tuple[BoundedText, ...] = Field(max_length=20)


class ResearchExtractionRequestV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.1"]
    research_run_id: UUID
    report_markdown: Annotated[str, StringConstraints(max_length=100_000)]
    registered_sources: tuple[RegisteredSourceV2, ...] = Field(min_length=1, max_length=100)
    known_signal_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    known_evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=500)
    max_claims: int = Field(ge=1, le=40)
    stale_after_days: int = Field(ge=1, le=3_650)
