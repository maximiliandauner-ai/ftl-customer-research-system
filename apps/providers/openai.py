from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, cast
from uuid import UUID

import openai
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from openai import OpenAI
from pydantic import ValidationError

from apps.operations.models import PipelineRun, ProviderCall, ProviderCallStatus
from apps.providers.contracts import (
    ProviderDiscoveryOutputV2,
    ProviderSourceV1,
    StructuredResearchResultV2,
    WebDiscoveryRequestV2,
    WebDiscoveryResultV2,
    WebResearchResultV2,
)
from apps.providers.models import ModelCapability, ModelPolicy
from apps.providers.policy import ActiveModelPolicyV1, capability_is_active
from apps.research.contracts import (
    ResearchExtractionRequestV2,
    ResearchExtractionV2,
    WebResearchRequestV2,
)

DISCOVERY_PROMPT_PATH = "discovery_candidate_search/v2.2.0.md"
RESEARCHER_PROMPT_PATH = "company_researcher/v2.1.0.md"
EXTRACTOR_PROMPT_PATH = "research_extractor/v2.1.0.md"


class ProviderError(RuntimeError):
    code = "OPENAI_PROVIDER_FAILED"


class ProviderPolicyBlocked(ProviderError):
    code = "OPENAI_TOOL_POLICY_INVALID"


class ProviderBudgetBlocked(ProviderError):
    code = "OPENAI_BUDGET_BLOCKED"


class ProviderRefused(ProviderError):
    code = "OPENAI_REFUSAL"


class ProviderIncomplete(ProviderError):
    code = "OPENAI_INCOMPLETE"


class ProviderSchemaInvalid(ProviderError):
    code = "OPENAI_SCHEMA_INVALID"


class ProviderRateLimited(ProviderError):
    code = "OPENAI_RATE_LIMITED"


class ProviderConcurrencyBlocked(ProviderError):
    code = "OPENAI_CONCURRENCY_BLOCKED"


class WebDiscoveryProvider(Protocol):
    def web_discovery(
        self,
        request: WebDiscoveryRequestV2,
        *,
        policy: ActiveModelPolicyV1,
        pipeline_run: PipelineRun,
    ) -> WebDiscoveryResultV2: ...


class StandardResearchProvider(Protocol):
    def web_research(
        self,
        request: WebResearchRequestV2,
        *,
        policy: ActiveModelPolicyV1,
        pipeline_run: PipelineRun,
    ) -> WebResearchResultV2: ...

    def research_extraction(
        self,
        request: ResearchExtractionRequestV2,
        *,
        policy: ActiveModelPolicyV1,
        pipeline_run: PipelineRun,
    ) -> StructuredResearchResultV2: ...


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _policy_snapshot(policy: ActiveModelPolicyV1) -> dict[str, object]:
    return policy.model_dump(mode="json")


def _safe_error_message(error: Exception) -> str:
    return (str(error).replace("\n", " ").strip() or error.__class__.__name__)[:500]


def _walk(value: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(value, dict):
        item = cast(dict[str, object], value)
        found.append(item)
        for nested in item.values():
            found.extend(_walk(nested))
    elif isinstance(value, list):
        for nested in cast(list[object], value):
            found.extend(_walk(nested))
    return found


def _response_sources(payload: dict[str, object]) -> tuple[ProviderSourceV1, ...]:
    sources: dict[str, ProviderSourceV1] = {}
    for item in _walk(payload):
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            continue
        raw_title = item.get("title")
        title = raw_title if isinstance(raw_title, str) else ""
        source_reference = ""
        for key in ("source_reference", "id", "source_id"):
            if isinstance(item.get(key), str):
                source_reference = cast(str, item[key])
                break
        sources[url] = ProviderSourceV1(
            url=url,
            title=title,
            source_reference=source_reference,
        )
    return tuple(sources.values())


def _web_calls(payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    return tuple(item for item in _walk(payload) if item.get("type") == "web_search_call")[:100]


def _citation_annotations(payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    return tuple(
        item
        for item in _walk(payload)
        if item.get("type") == "url_citation"
        or (isinstance(item.get("url"), str) and ("start_index" in item or "end_index" in item))
    )[:500]


def _contains_refusal(payload: dict[str, object]) -> bool:
    return any(item.get("type") == "refusal" for item in _walk(payload))


def _prompt_text(relative_path: str) -> str:
    allowed = {DISCOVERY_PROMPT_PATH, RESEARCHER_PROMPT_PATH, EXTRACTOR_PROMPT_PATH}
    if relative_path not in allowed:
        raise ProviderPolicyBlocked("The requested prompt is outside the reviewed registry.")
    return (settings.BASE_DIR / "prompts" / relative_path).read_text(encoding="utf-8")


def _usage_payload(response: object) -> dict[str, object]:
    usage_model = getattr(response, "usage", None)
    if usage_model is None:
        return {}
    return cast(dict[str, object], usage_model.model_dump(mode="json"))


class OpenAIResponsesProvider:
    def __init__(self, *, api_key: str, client: Any | None = None) -> None:
        self._client: Any = client or OpenAI(api_key=api_key, timeout=60.0, max_retries=1)

    def _validate_policy(
        self,
        *,
        maximum_cost_usd: float,
        policy: ActiveModelPolicyV1,
        require_web_search: bool,
    ) -> None:
        if maximum_cost_usd > policy.max_cost_usd:
            raise ProviderBudgetBlocked("The request exceeds the active provider cost policy.")
        if not capability_is_active(policy):
            raise ProviderPolicyBlocked("The selected model capability is not active.")
        if not (policy.supports_responses and policy.supports_structured_outputs):
            raise ProviderPolicyBlocked("The active model policy lacks required Responses support.")
        if require_web_search and not (
            policy.supports_web_search and policy.web_search_tool_type == "web_search"
        ):
            raise ProviderPolicyBlocked("The active model policy does not support web search.")
        if policy.reasoning_effort not in policy.allowed_reasoning_efforts:
            raise ProviderPolicyBlocked("The reasoning effort is not allowed by the capability.")
        if not policy.store and not policy.supports_store_false:
            raise ProviderPolicyBlocked("The active capability does not support store=false.")

    @staticmethod
    def _reserved_spend(*, since: datetime, exclude_call_id: UUID) -> Decimal:
        calls = ProviderCall.objects.filter(
            provider="openai",
            started_at__gte=since,
            status__in=(
                ProviderCallStatus.RUNNING,
                ProviderCallStatus.COMPLETE,
                ProviderCallStatus.INCOMPLETE,
            ),
        ).exclude(pk=exclude_call_id)
        total = Decimal("0")
        for metadata in calls.values_list("cost_metadata", flat=True):
            if isinstance(metadata, dict):
                total += Decimal(str(metadata.get("maximum_cost_usd", 0)))
        return total

    def _authorize_call(
        self,
        call: ProviderCall,
        *,
        maximum_cost_usd: float,
        policy: ActiveModelPolicyV1,
        operation: str,
        require_web_search: bool,
    ) -> None:
        with transaction.atomic():
            try:
                policy_record = ModelPolicy.objects.select_for_update().get(
                    policy_sha256=policy.policy_sha256,
                    active=True,
                )
            except ModelPolicy.DoesNotExist as exc:
                raise ProviderPolicyBlocked(
                    "The immutable provider policy is no longer active."
                ) from exc
            ModelCapability.objects.select_for_update().get(pk=policy_record.capability_id)
            self._validate_policy(
                maximum_cost_usd=maximum_cost_usd,
                policy=policy,
                require_web_search=require_web_search,
            )
            running = (
                ProviderCall.objects.filter(
                    provider="openai",
                    operation=operation,
                    status=ProviderCallStatus.RUNNING,
                )
                .exclude(pk=call.pk)
                .count()
            )
            concurrency_limit = min(
                policy.max_concurrent_calls,
                settings.RUNTIME_SETTINGS.openai_max_concurrent_standard_calls,
            )
            if running >= concurrency_limit:
                raise ProviderConcurrencyBlocked(
                    "The discovery provider concurrency limit is currently full."
                )
            now = timezone.now()
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            month_start = day_start.replace(day=1)
            requested = Decimal(str(maximum_cost_usd))
            daily_limit = min(
                Decimal(str(policy.max_daily_cost_usd)),
                settings.RUNTIME_SETTINGS.openai_daily_budget_usd,
            )
            monthly_limit = min(
                Decimal(str(policy.max_monthly_cost_usd)),
                settings.RUNTIME_SETTINGS.openai_monthly_budget_usd,
            )
            if (
                self._reserved_spend(since=day_start, exclude_call_id=call.pk) + requested
                > daily_limit
            ):
                raise ProviderBudgetBlocked("The daily provider budget is exhausted.")
            if (
                self._reserved_spend(since=month_start, exclude_call_id=call.pk) + requested
                > monthly_limit
            ):
                raise ProviderBudgetBlocked("The monthly provider budget is exhausted.")
            call.status = ProviderCallStatus.RUNNING
            call.started_at = now
            call.save(update_fields=("status", "started_at"))

    def web_discovery(
        self,
        request: WebDiscoveryRequestV2,
        *,
        policy: ActiveModelPolicyV1,
        pipeline_run: PipelineRun,
    ) -> WebDiscoveryResultV2:
        instructions = _prompt_text(DISCOVERY_PROMPT_PATH)
        request_hash = _hash_payload(
            {
                "instructions": instructions,
                "request": request.model_dump(mode="json"),
                "policy": policy.model_dump(mode="json"),
            }
        )
        call = ProviderCall.objects.create(
            pipeline_run=pipeline_run,
            provider="openai",
            operation="discovery.web_search",
            request_sha256=request_hash,
            model_policy_snapshot=_policy_snapshot(policy),
            status=ProviderCallStatus.QUEUED,
            retention_class="store_false",
            cost_metadata={
                "maximum_cost_usd": request.max_provider_cost_usd,
                "pricing_policy_version": "unpriced-1.0",
            },
        )
        try:
            self._authorize_call(
                call,
                maximum_cost_usd=request.max_provider_cost_usd,
                policy=policy,
                operation="discovery.web_search",
                require_web_search=True,
            )
            include = (
                ["web_search_call.action.sources"] if policy.supports_source_list_include else []
            )
            response = self._client.responses.parse(
                model=policy.model_id,
                instructions=instructions,
                input=[
                    {
                        "role": "user",
                        "content": json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
                    }
                ],
                tools=[
                    {
                        "type": "web_search",
                        "search_context_size": policy.search_context_size,
                    }
                ],
                include=include,
                reasoning={"effort": policy.reasoning_effort},
                max_tool_calls=min(request.max_tool_calls, policy.max_tool_calls),
                max_output_tokens=policy.max_output_tokens,
                store=policy.store,
                text_format=ProviderDiscoveryOutputV2,
            )
            payload = cast(dict[str, object], response.model_dump(mode="json"))
            response_id = str(response.id)
            call.external_response_id = response_id
            call.save(update_fields=("external_response_id",))
            if _contains_refusal(payload):
                raise ProviderRefused("The provider refused the discovery request.")
            if str(response.status) != "completed":
                raise ProviderIncomplete("The provider response did not complete.")
            parsed = response.output_parsed
            if not isinstance(parsed, ProviderDiscoveryOutputV2):
                raise ProviderSchemaInvalid("The provider returned no valid structured output.")
            usage_model = getattr(response, "usage", None)
            usage = (
                cast(dict[str, object], usage_model.model_dump(mode="json"))
                if usage_model is not None
                else {}
            )
            sources = _response_sources(payload)
            tool_calls = _web_calls(payload)
            with transaction.atomic():
                call.status = ProviderCallStatus.COMPLETE
                call.usage = usage
                call.tool_calls = list(tool_calls)
                call.completed_at = timezone.now()
                call.save(
                    update_fields=(
                        "external_response_id",
                        "status",
                        "usage",
                        "tool_calls",
                        "completed_at",
                    )
                )
            return WebDiscoveryResultV2(
                output=parsed,
                response_id=response_id,
                response_model=str(response.model),
                sources=sources,
                usage=usage,
                tool_calls=tool_calls,
            )
        except ProviderError as exc:
            self._fail_call(call, exc.code, exc)
            raise
        except ValidationError as exc:
            schema_failure = ProviderSchemaInvalid("The provider output failed strict validation.")
            self._fail_call(call, schema_failure.code, schema_failure)
            raise schema_failure from exc
        except openai.RateLimitError as exc:
            rate_failure = ProviderRateLimited("The provider rate limit was reached.")
            self._fail_call(call, rate_failure.code, rate_failure)
            raise rate_failure from exc
        except openai.APIError as exc:
            api_failure = ProviderError("The provider request failed.")
            self._fail_call(call, api_failure.code, api_failure)
            raise api_failure from exc

    def web_research(
        self,
        request: WebResearchRequestV2,
        *,
        policy: ActiveModelPolicyV1,
        pipeline_run: PipelineRun,
    ) -> WebResearchResultV2:
        instructions = _prompt_text(RESEARCHER_PROMPT_PATH)
        request_hash = _hash_payload(
            {
                "instructions": instructions,
                "request": request.model_dump(mode="json"),
                "policy": policy.model_dump(mode="json"),
            }
        )
        call = ProviderCall.objects.create(
            pipeline_run=pipeline_run,
            provider="openai",
            operation="research.web_search",
            request_sha256=request_hash,
            model_policy_snapshot=_policy_snapshot(policy),
            status=ProviderCallStatus.QUEUED,
            retention_class="research_report_store_false",
            cost_metadata={
                "maximum_cost_usd": request.max_provider_cost_usd,
                "pricing_policy_version": "unpriced-1.0",
            },
        )
        try:
            self._authorize_call(
                call,
                maximum_cost_usd=request.max_provider_cost_usd,
                policy=policy,
                operation="research.web_search",
                require_web_search=True,
            )
            include = (
                ["web_search_call.action.sources"] if policy.supports_source_list_include else []
            )
            response = self._client.responses.create(
                model=policy.model_id,
                instructions=instructions,
                input=[
                    {
                        "role": "user",
                        "content": json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
                    }
                ],
                tools=[
                    {
                        "type": "web_search",
                        "search_context_size": policy.search_context_size,
                    }
                ],
                include=include,
                reasoning={"effort": policy.reasoning_effort},
                max_tool_calls=min(request.max_tool_calls, policy.max_tool_calls),
                max_output_tokens=policy.max_output_tokens,
                store=policy.store,
            )
            payload = cast(dict[str, object], response.model_dump(mode="json"))
            response_id = str(response.id)
            call.external_response_id = response_id
            call.save(update_fields=("external_response_id",))
            if _contains_refusal(payload):
                raise ProviderRefused("The provider refused the research request.")
            if str(response.status) != "completed":
                raise ProviderIncomplete("The public research response did not complete.")
            report = str(getattr(response, "output_text", "")).strip()
            if not report:
                raise ProviderIncomplete("The public research response contained no report.")
            sources = _response_sources(payload)
            if not sources:
                raise ProviderSchemaInvalid("The public research response has no provider sources.")
            usage = _usage_payload(response)
            tool_calls = _web_calls(payload)
            citations = _citation_annotations(payload)
            call.status = ProviderCallStatus.COMPLETE
            call.usage = usage
            call.tool_calls = list(tool_calls)
            call.completed_at = timezone.now()
            call.save(
                update_fields=(
                    "external_response_id",
                    "status",
                    "usage",
                    "tool_calls",
                    "completed_at",
                )
            )
            return WebResearchResultV2(
                report_markdown=report,
                response_id=response_id,
                response_model=str(response.model),
                sources=sources,
                citation_annotations=citations,
                usage=usage,
                tool_calls=tool_calls,
            )
        except ProviderError as exc:
            self._fail_call(call, exc.code, exc)
            raise
        except ValidationError as exc:
            schema_failure = ProviderSchemaInvalid("The research result failed strict validation.")
            self._fail_call(call, schema_failure.code, schema_failure)
            raise schema_failure from exc
        except openai.RateLimitError as exc:
            rate_failure = ProviderRateLimited("The provider rate limit was reached.")
            self._fail_call(call, rate_failure.code, rate_failure)
            raise rate_failure from exc
        except openai.APIError as exc:
            api_failure = ProviderError("The public research provider request failed.")
            self._fail_call(call, api_failure.code, api_failure)
            raise api_failure from exc

    def research_extraction(
        self,
        request: ResearchExtractionRequestV2,
        *,
        policy: ActiveModelPolicyV1,
        pipeline_run: PipelineRun,
    ) -> StructuredResearchResultV2:
        instructions = _prompt_text(EXTRACTOR_PROMPT_PATH)
        request_hash = _hash_payload(
            {
                "instructions": instructions,
                "request": request.model_dump(mode="json"),
                "policy": policy.model_dump(mode="json"),
            }
        )
        call = ProviderCall.objects.create(
            pipeline_run=pipeline_run,
            provider="openai",
            operation="research.extract",
            request_sha256=request_hash,
            model_policy_snapshot=_policy_snapshot(policy),
            status=ProviderCallStatus.QUEUED,
            retention_class="research_extraction_store_false",
            cost_metadata={
                "maximum_cost_usd": policy.max_cost_usd,
                "pricing_policy_version": "unpriced-1.0",
            },
        )
        try:
            self._authorize_call(
                call,
                maximum_cost_usd=policy.max_cost_usd,
                policy=policy,
                operation="research.extract",
                require_web_search=False,
            )
            response = self._client.responses.parse(
                model=policy.model_id,
                instructions=instructions,
                input=[
                    {
                        "role": "user",
                        "content": json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
                    }
                ],
                reasoning={"effort": policy.reasoning_effort},
                max_output_tokens=policy.max_output_tokens,
                store=policy.store,
                text_format=ResearchExtractionV2,
            )
            payload = cast(dict[str, object], response.model_dump(mode="json"))
            response_id = str(response.id)
            call.external_response_id = response_id
            call.save(update_fields=("external_response_id",))
            if _contains_refusal(payload):
                raise ProviderRefused("The provider refused the extraction request.")
            if str(response.status) != "completed":
                raise ProviderIncomplete("The extraction response did not complete.")
            parsed = response.output_parsed
            if not isinstance(parsed, ResearchExtractionV2):
                raise ProviderSchemaInvalid("The provider returned no valid research extraction.")
            usage = _usage_payload(response)
            call.status = ProviderCallStatus.COMPLETE
            call.usage = usage
            call.completed_at = timezone.now()
            call.save(
                update_fields=(
                    "external_response_id",
                    "status",
                    "usage",
                    "completed_at",
                )
            )
            return StructuredResearchResultV2(
                output=parsed,
                response_id=response_id,
                response_model=str(response.model),
                usage=usage,
            )
        except ProviderError as exc:
            self._fail_call(call, exc.code, exc)
            raise
        except ValidationError as exc:
            schema_failure = ProviderSchemaInvalid(
                "The extraction output failed strict validation."
            )
            self._fail_call(call, schema_failure.code, schema_failure)
            raise schema_failure from exc
        except openai.RateLimitError as exc:
            rate_failure = ProviderRateLimited("The provider rate limit was reached.")
            self._fail_call(call, rate_failure.code, rate_failure)
            raise rate_failure from exc
        except openai.APIError as exc:
            api_failure = ProviderError("The extraction provider request failed.")
            self._fail_call(call, api_failure.code, api_failure)
            raise api_failure from exc

    @staticmethod
    def _fail_call(call: ProviderCall, code: str, error: Exception) -> None:
        call.status = (
            ProviderCallStatus.REFUSED if code == "OPENAI_REFUSAL" else ProviderCallStatus.FAILED
        )
        if code == "OPENAI_INCOMPLETE":
            call.status = ProviderCallStatus.INCOMPLETE
        call.safe_error_code = code
        call.safe_error_message = _safe_error_message(error)
        call.completed_at = timezone.now()
        call.save(
            update_fields=(
                "external_response_id",
                "status",
                "safe_error_code",
                "safe_error_message",
                "completed_at",
            )
        )
