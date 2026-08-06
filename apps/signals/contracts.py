from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

BoundedText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1_000)]
EvidenceId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^EV-[0-9]{6}$", max_length=9),
]


class SignalCandidateV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    signal_type: Literal[
        "capability_hiring",
        "material_description_change",
        "role_reposted",
        "role_reopened",
        "role_closed",
    ]
    event_kind: Literal["created", "material", "closed", "reopened"]
    capability_tags: tuple[BoundedText, ...] = Field(max_length=20)
    supporting_evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=50)
    confidence: float = Field(ge=0.0, le=1.0)
    concise_rationale: BoundedText
    review_flags: tuple[BoundedText, ...] = Field(max_length=20)


class SignalDetectionResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.0"]
    prompt_version: Literal["2.0.0"]
    signals: tuple[SignalCandidateV2, ...] = Field(max_length=20)
    no_signal_reason: BoundedText | None
    unknowns: tuple[BoundedText, ...] = Field(max_length=50)

    @model_validator(mode="after")
    def require_consistent_no_signal_reason(self) -> SignalDetectionResultV2:
        if not self.signals and not self.no_signal_reason:
            raise ValueError("A no-signal result requires a reason.")
        if self.signals and self.no_signal_reason:
            raise ValueError("A signal result cannot also include a no-signal reason.")
        return self


class SignalDetectionInputV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    change_event_id: Annotated[str, StringConstraints(max_length=36)]
    change_type: Literal["created", "material", "closed", "reopened"]
    snapshot_id: Annotated[str, StringConstraints(max_length=36)]
    evidence_catalog_id: Annotated[str, StringConstraints(max_length=36)]
    allowed_signal_types: tuple[BoundedText, ...]
    allowed_capability_tags: tuple[BoundedText, ...]
    evidence_items: tuple[dict[str, str], ...] = Field(max_length=1_000)
