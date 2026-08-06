from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from apps.providers.models import ModelPolicy


class ActiveModelPolicyV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    policy_key: str
    version: str
    model_id: str
    capability_status: Literal["active", "legacy", "deprecated", "disabled"]
    supports_responses: bool
    supports_structured_outputs: bool
    supports_web_search: bool
    web_search_tool_type: str
    supports_source_list_include: bool
    supports_store_false: bool
    allowed_reasoning_efforts: tuple[str, ...]
    reasoning_effort: str
    search_context_size: str
    max_tool_calls: int
    max_output_tokens: int
    max_cost_usd: float
    max_daily_cost_usd: float
    max_monthly_cost_usd: float
    max_concurrent_calls: int
    store: bool
    policy_sha256: str


def active_model_policy(policy_key: str) -> ActiveModelPolicyV1:
    policy = ModelPolicy.objects.select_related("capability").get(
        policy_key=policy_key,
        active=True,
    )
    capability = policy.capability
    return ActiveModelPolicyV1(
        policy_key=policy.policy_key,
        version=policy.version,
        model_id=capability.model_id,
        capability_status=capability.status,  # type: ignore[arg-type]
        supports_responses=capability.supports_responses,
        supports_structured_outputs=capability.supports_structured_outputs,
        supports_web_search=capability.supports_web_search,
        web_search_tool_type=capability.web_search_tool_type,
        supports_source_list_include=capability.supports_source_list_include,
        supports_store_false=capability.supports_store_false,
        allowed_reasoning_efforts=tuple(capability.allowed_reasoning_efforts),
        reasoning_effort=policy.reasoning_effort,
        search_context_size=policy.search_context_size,
        max_tool_calls=policy.max_tool_calls,
        max_output_tokens=policy.max_output_tokens,
        max_cost_usd=float(policy.max_cost_usd),
        max_daily_cost_usd=float(policy.max_daily_cost_usd),
        max_monthly_cost_usd=float(policy.max_monthly_cost_usd),
        max_concurrent_calls=policy.max_concurrent_calls,
        store=policy.store,
        policy_sha256=policy.policy_sha256,
    )


def capability_is_active(policy: ActiveModelPolicyV1) -> bool:
    return policy.capability_status == "active"
