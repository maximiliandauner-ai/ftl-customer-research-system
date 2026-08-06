from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
DomainText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


class SearchDefinitionInputV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    definition_key: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$"
        ),
    ]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4_000)] = ""
    query_template: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)
    ]
    language: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=16)]
    countries: tuple[Annotated[str, StringConstraints(min_length=2, max_length=2)], ...] = Field(
        default=(), max_length=20
    )
    locations: tuple[ShortText, ...] = Field(default=(), max_length=50)
    capability_clusters: tuple[ShortText, ...] = Field(default=(), max_length=50)
    positive_terms: tuple[ShortText, ...] = Field(min_length=1, max_length=100)
    negative_terms: tuple[ShortText, ...] = Field(default=(), max_length=100)
    preferred_domains: tuple[DomainText, ...] = Field(default=(), max_length=100)
    excluded_domains: tuple[DomainText, ...] = Field(default=(), max_length=100)
    source_type_filters: tuple[
        Literal["job_posting", "career_page", "personio", "greenhouse", "lever", "ashby"], ...
    ] = Field(default=("job_posting", "career_page"), max_length=10)
    schedule_key: Literal["daily_morning", "manual_only"] = "daily_morning"
    max_candidates: int = Field(default=50, ge=1, le=200)
    lookback_days: int = Field(default=21, ge=1, le=365)

    @field_validator("countries")
    @classmethod
    def uppercase_countries(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(value.upper() for value in values)


class DiscoveryRunRequestV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    max_tool_calls: int = Field(default=8, ge=1, le=50)
    max_provider_cost_usd: float = Field(default=0.50, gt=0.0, le=100.0)
