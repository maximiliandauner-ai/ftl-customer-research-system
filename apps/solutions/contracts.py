from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000)]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_.-]{1,99}$")]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Layer = Literal["create", "build", "deploy", "enable"]


class EvidenceBoundStatementV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    statement: LongText
    kind: Literal["observed_fact", "inference", "hypothesis"]
    confidence: float = Field(ge=0, le=1)
    evidence_refs: tuple[Reference, ...] = Field(min_length=1, max_length=50)


class SolutionPhaseV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    order: int = Field(ge=1, le=4)
    name: ShortText
    objective: LongText
    deliverables: tuple[ShortText, ...] = Field(min_length=1, max_length=20)
    client_inputs: tuple[ShortText, ...] = Field(max_length=20)
    success_criteria: tuple[ShortText, ...] = Field(min_length=1, max_length=20)
    dependencies: tuple[ShortText, ...] = Field(max_length=20)
    evidence_refs: tuple[Reference, ...] = Field(min_length=1, max_length=50)
    assumptions: tuple[ShortText, ...] = Field(max_length=20)
    optional: bool


class InfrastructureV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    recommended_mode: Literal[
        "unknown", "cloud", "private_cloud", "on_premises", "hybrid", "not_required"
    ]
    rationale: LongText
    evidence_refs: tuple[Reference, ...] = Field(max_length=50)
    assumptions: tuple[ShortText, ...] = Field(max_length=20)
    discovery_questions: tuple[ShortText, ...] = Field(max_length=20)


class BuyerRoleRequirementV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    owner_type: Literal["operational_owner", "technical_owner", "commercial_sponsor"]
    responsibility: LongText


class SolutionHypothesisV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.1"]
    prompt_version: Literal["2.1.0"]
    opportunity_name: ShortText
    problem_hypothesis: EvidenceBoundStatementV2
    entry_offer: Key
    ftl_layers: tuple[Layer, ...] = Field(min_length=1, max_length=4)
    phases: tuple[SolutionPhaseV2, ...] = Field(min_length=1, max_length=4)
    infrastructure: InfrastructureV2
    long_term_operating_model: Literal[
        "done_for_you",
        "managed_capability",
        "capability_transfer",
        "hybrid_partnership",
        "unknown",
    ]
    immediate_value: LongText
    long_term_value: LongText
    internal_hire_complementarity: LongText
    buyer_role_requirements: tuple[BuyerRoleRequirementV2, ...] = Field(max_length=6)
    asset_match_requirements: tuple[ShortText, ...] = Field(max_length=10)
    discovery_questions: tuple[ShortText, ...] = Field(max_length=20)
    risks: tuple[ShortText, ...] = Field(max_length=20)
    unknowns: tuple[ShortText, ...] = Field(max_length=30)
    do_not_claim: tuple[ShortText, ...] = Field(max_length=50)
    confidence: float = Field(ge=0, le=1)


class SelectedAssetV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    asset_id: Key
    relevance_reason: LongText
    priority: int = Field(ge=1, le=2)
    supported_solution_phase: int = Field(ge=1, le=4)


class AssetMatchOutputV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.1"]
    prompt_version: Literal["2.1.0"]
    solution_id: UUID
    selected_assets: tuple[SelectedAssetV2, ...] = Field(max_length=2)
    excluded_asset_ids: tuple[Key, ...] = Field(max_length=2_000)
    unknowns: tuple[ShortText, ...] = Field(max_length=20)
    review_flags: tuple[ShortText, ...] = Field(max_length=20)
