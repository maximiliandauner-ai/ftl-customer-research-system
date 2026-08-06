from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubmitPublicSourceV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1.0"] = "1.0"
    requested_url: str = Field(min_length=8, max_length=4096)
    company_name: str | None = Field(default=None, max_length=500)
    company_domain: str | None = Field(default=None, max_length=255)
    idempotency_key: str = Field(min_length=8, max_length=255, pattern=r"^[a-zA-Z0-9:._-]+$")
    request_id: UUID | None = None
    public_source_confirmed: Literal[True]

    @field_validator("company_name", "company_domain", mode="before")
    @classmethod
    def blank_optional_strings_are_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class FetchSourcePayloadV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline_run_id: UUID
    object_id: UUID


class SafeFetchResultV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    schema_version: Literal["1.0"] = "1.0"
    requested_url: str
    final_url: str
    status_code: int = Field(ge=100, le=599)
    retrieved_at_iso: str
    content_type: str = Field(max_length=255)
    encoding: str = Field(max_length=64)
    headers_filtered: dict[str, str]
    body: bytes
    body_sha256: str = Field(min_length=64, max_length=64)
    body_size_bytes: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    redirect_chain: list[dict[str, object]]
    network_policy: Literal["allowed"] = "allowed"
    robots_policy: Literal["allowed", "unknown", "not_applicable"] = "unknown"
    retryable: bool = False
    warnings: tuple[str, ...] = ()
