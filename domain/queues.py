from typing import Literal

from pydantic import BaseModel, ConfigDict

QueueName = Literal[
    "discovery",
    "fetch",
    "parse",
    "classification",
    "aggregation",
    "research",
    "deep_research",
    "solution_design",
    "asset_matching",
    "contact_enrichment",
    "drafting",
    "review",
    "maintenance",
]


class QueuePolicyV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.1"] = "1.1"
    exchange_namespace: Literal["ftl.v1"] = "ftl.v1"
    names: tuple[QueueName, ...]

    def exchange_name(self, queue_name: QueueName) -> str:
        return f"{self.exchange_namespace}.{queue_name}"


QUEUE_POLICY = QueuePolicyV1(
    names=(
        "discovery",
        "fetch",
        "parse",
        "classification",
        "aggregation",
        "research",
        "deep_research",
        "solution_design",
        "asset_matching",
        "contact_enrichment",
        "drafting",
        "review",
        "maintenance",
    )
)
