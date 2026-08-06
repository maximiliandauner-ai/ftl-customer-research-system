from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Key = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_.-]{1,99}$")]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8_000)]
UrlText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=4_096)]
Layer = Literal["create", "build", "deploy", "enable"]


class OfferModuleV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    key: Key
    version: int = Field(ge=1, le=10_000)
    title: ShortText
    ftl_layers: tuple[Layer, ...] = Field(min_length=1, max_length=4)
    problem_patterns: tuple[Key, ...] = Field(max_length=30)
    description: LongText
    typical_deliverables: tuple[ShortText, ...] = Field(max_length=30)
    suitable_client_profiles: tuple[ShortText, ...] = Field(max_length=30)
    infrastructure_options: tuple[
        Literal["cloud", "private_cloud", "on_premises", "hybrid", "not_required"], ...
    ] = Field(max_length=5)
    exclusions: tuple[ShortText, ...] = Field(max_length=30)
    approved: bool


class ApprovedClaimV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    claim_key: Key
    version: int = Field(ge=1, le=10_000)
    full_wording: LongText
    short_wording: ShortText
    claim_type: Literal["identity", "capability", "case_study_result", "technical"]
    supporting_asset_ids: tuple[Key, ...] = Field(max_length=30)
    allowed_audiences: tuple[Key, ...] = Field(min_length=1, max_length=20)
    allowed_languages: tuple[Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")], ...] = Field(
        min_length=1, max_length=20
    )
    paraphrase_allowed: bool
    strengthening_prohibited: bool
    valid_from: date
    review_due_at: date


class ProhibitedClaimV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    claim_key: Key
    wording: LongText
    reason: ShortText


class AssetV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    asset_id: Key
    version: int = Field(ge=1, le=10_000)
    title: ShortText
    type: Key
    public_url: UrlText
    short_description: ShortText
    detailed_description: LongText
    capability_tags: tuple[Key, ...] = Field(max_length=50)
    ftl_layers: tuple[Layer, ...] = Field(min_length=1, max_length=4)
    industries: tuple[Key, ...] = Field(max_length=50)
    languages: tuple[Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")], ...] = Field(
        min_length=1, max_length=20
    )
    audiences: tuple[Key, ...] = Field(min_length=1, max_length=20)
    confidentiality: Literal["public", "internal", "confidential_client", "embargoed"]
    approved_for_external_use: bool
    status: Literal["live", "preview", "archived"]
    last_reviewed_at: datetime
    url_last_checked_at: datetime | None


class KnowledgeCatalogV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.1"]
    offers: tuple[OfferModuleV2, ...] = Field(max_length=500)
    approved_claims: tuple[ApprovedClaimV2, ...] = Field(max_length=2_000)
    prohibited_claims: tuple[ProhibitedClaimV2, ...] = Field(max_length=2_000)
    assets: tuple[AssetV2, ...] = Field(max_length=2_000)
