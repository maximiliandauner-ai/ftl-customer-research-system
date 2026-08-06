from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

BoundedText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1_000)]
EvidenceId = Annotated[str, StringConstraints(pattern=r"^EV-[0-9]{6}$", max_length=9)]


class CapabilityClusterV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    key: BoundedText
    confidence: float = Field(ge=0, le=1)
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=50)


class CapabilityGapV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    key: BoundedText
    confidence: float = Field(ge=0, le=1)
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=50)
    concise_rationale: BoundedText


class EntryOfferCandidateV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    key: BoundedText
    confidence: float = Field(ge=0, le=1)
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=50)


class NumericJudgmentV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)


class CategoricalJudgmentV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    value: Literal["low", "medium", "high", "unknown"]
    confidence: float = Field(ge=0, le=1)


class ComponentJudgmentsV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    task_overlap: NumericJudgmentV2
    reusable_system_potential: NumericJudgmentV2
    enablement_potential: NumericJudgmentV2
    infrastructure_relevance: CategoricalJudgmentV2
    vendor_receptivity: CategoricalJudgmentV2


class CapabilityAssessmentV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.1"]
    prompt_version: Literal["2.1.0"]
    capability_clusters: tuple[CapabilityClusterV2, ...] = Field(max_length=30)
    capability_gaps: tuple[CapabilityGapV2, ...] = Field(max_length=30)
    opportunity_mode: Literal[
        "employment_only",
        "external_service",
        "hybrid",
        "watch_signal",
        "irrelevant",
        "unknown",
    ]
    mode_confidence: float = Field(ge=0, le=1)
    mode_evidence_ids: tuple[EvidenceId, ...] = Field(max_length=50)
    mode_rationale: BoundedText
    recommended_ftl_layers: tuple[Literal["create", "build", "deploy", "enable"], ...]
    entry_offer_candidates: tuple[EntryOfferCandidateV2, ...] = Field(max_length=20)
    component_judgments: ComponentJudgmentsV2
    unknowns: tuple[BoundedText, ...] = Field(max_length=50)
    review_flags: tuple[BoundedText, ...] = Field(max_length=20)
