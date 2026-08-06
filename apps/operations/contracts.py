from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateCheckpointCommandV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1.0"] = "1.0"
    idempotency_key: str = Field(min_length=8, max_length=255, pattern=r"^[a-zA-Z0-9:._-]+$")
    request_id: UUID | None = None


class CheckpointPayloadV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline_run_id: UUID


class TaskEnvelopeV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["2.1"] = "2.1"
    outbox_id: UUID
    pipeline_run_id: UUID
    command_type: str = Field(min_length=3, max_length=160)
    object_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=255)
    requested_by: str = Field(min_length=1, max_length=80)
    request_id: UUID | None = None
    policy_version: Literal["2.1"] = "2.1"
    force: bool = False

    @field_validator("requested_by")
    @classmethod
    def requested_by_is_safe(cls, value: str) -> str:
        if value != "system" and not value.startswith("user:"):
            raise ValueError("requested_by must be system or an application user reference")
        return value
