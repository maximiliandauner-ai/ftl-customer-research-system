from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
EvidenceText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1_000)]
UrlText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4_096)]


class ParsedCompanyFieldV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    field_name: Literal[
        "legal_name",
        "company_type",
        "industry_key",
        "headquarters_city",
        "headquarters_country",
        "employee_range",
        "description",
    ]
    value: ShortText
    evidence_excerpt: EvidenceText
    extraction_method: Annotated[str, StringConstraints(max_length=64)]
    confidence: float = Field(ge=0, le=1)


class ParsedCompanyPageV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    identity_names: tuple[ShortText, ...] = Field(default=(), max_length=30)
    fields: tuple[ParsedCompanyFieldV1, ...] = Field(default=(), max_length=50)
    discovered_urls: tuple[UrlText, ...] = Field(default=(), max_length=50)
    warnings: tuple[ShortText, ...] = Field(default=(), max_length=30)
