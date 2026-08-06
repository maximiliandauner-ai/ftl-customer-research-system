from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500_000)]
UrlText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4_096)]


class ParsedLocationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    display_text: ShortText
    city: ShortText = ""
    region: ShortText = ""
    country: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2)] = ""
    postal_code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] = ""
    remote: bool = False
    workplace_type: Literal["onsite", "hybrid", "remote", "unknown"] = "unknown"

    @field_validator("country")
    @classmethod
    def uppercase_country(cls, value: str) -> str:
        return value.upper()


class ParsedSectionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    heading: ShortText
    text: LongText
    kind: Literal["description", "responsibilities", "requirements", "benefits", "other"]


class ParsedPostingV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    external_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    canonical_url: UrlText
    apply_url: UrlText = ""
    company_name: ShortText = ""
    company_url: UrlText = ""
    department: ShortText = ""
    team: ShortText = ""
    employment_type: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    language: Annotated[str, StringConstraints(strip_whitespace=True, max_length=16)] = ""
    published_at: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] = ""
    valid_through: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] = ""
    is_open: bool = True
    description_text: LongText
    sections: tuple[ParsedSectionV1, ...] = Field(default=(), max_length=100)
    locations: tuple[ParsedLocationV1, ...] = Field(default=(), max_length=100)


class ConnectorParseResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    connector_key: Literal["personio", "greenhouse", "lever", "ashby", "json_ld", "generic_html"]
    connector_version: Annotated[str, StringConstraints(max_length=32)]
    collection_complete: bool = False
    postings: tuple[ParsedPostingV1, ...] = Field(default=(), max_length=2_000)
    warnings: tuple[ShortText, ...] = Field(default=(), max_length=100)
