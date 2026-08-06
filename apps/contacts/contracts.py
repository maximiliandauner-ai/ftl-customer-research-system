from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

BoundedText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
SourceId = Annotated[str, StringConstraints(pattern=r"^SRC-[0-9]{6}$", max_length=10)]
EvidenceId = Annotated[str, StringConstraints(pattern=r"^(?:EV|CEV)-[0-9]{6}$", max_length=10)]
ClaimId = Annotated[str, StringConstraints(pattern=r"^CLM-[0-9]{6}$", max_length=10)]


class BuyerRoleHypothesisV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    role_key: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,99}$")]
    owner_type: Literal[
        "economic_owner",
        "operational_owner",
        "technical_owner",
        "creative_owner",
        "learning_owner",
        "procurement_or_legal_influencer",
        "executive_sponsor",
        "unknown",
    ]
    responsibility_match: BoundedText
    priority: int = Field(ge=1, le=20)
    confidence: float = Field(ge=0, le=1)
    source_ids: tuple[SourceId, ...] = Field(max_length=50)
    claim_ids: tuple[ClaimId, ...] = Field(max_length=50)
    evidence_ids: tuple[EvidenceId, ...] = Field(max_length=100)
    unknowns: tuple[BoundedText, ...] = Field(max_length=20)


class BuyerRoleResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.1"]
    prompt_version: Literal["2.1.0"]
    solution_version_id: UUID
    roles: tuple[BuyerRoleHypothesisV2, ...] = Field(min_length=1, max_length=20)
    unknowns: tuple[BoundedText, ...] = Field(max_length=30)
    review_flags: tuple[BoundedText, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def unique_role_keys_and_priorities(self) -> BuyerRoleResultV2:
        keys = [role.role_key for role in self.roles]
        priorities = [role.priority for role in self.roles]
        if len(keys) != len(set(keys)) or len(priorities) != len(set(priorities)):
            raise ValueError("Buyer role keys and priorities must be unique.")
        return self


class ContactRouteItemV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    route_type: Literal[
        "role_email",
        "individual_business_email",
        "contact_form",
        "professional_profile",
        "phone",
        "other_public_route",
    ]
    route_origin: Literal["public_source"]
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=4_096)]
    contact_person_id: UUID | None
    buyer_role_key: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,99}$")]
    observation_status: Literal[
        "published_officially",
        "published_third_party",
        "human_confirmed",
        "unconfirmed",
        "disputed",
    ]
    freshness_status: Literal["current", "stale", "unknown"]
    deliverability_status: Literal["unknown"]
    outreach_eligibility: Literal["unreviewed"]
    source_ids: tuple[SourceId, ...] = Field(min_length=1, max_length=50)
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=100)
    retrieved_at: Annotated[str, StringConstraints(max_length=40)]
    confidence: float = Field(ge=0, le=1)


class ContactRouteResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.1"]
    prompt_version: Literal["2.1.0"]
    routes: tuple[ContactRouteItemV2, ...] = Field(max_length=100)
    unknowns: tuple[BoundedText, ...] = Field(max_length=30)
    review_flags: tuple[BoundedText, ...] = Field(max_length=20)
