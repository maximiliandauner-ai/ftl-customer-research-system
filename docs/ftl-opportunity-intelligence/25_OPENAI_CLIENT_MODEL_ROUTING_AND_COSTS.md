# 25 — OpenAI Responses API Client, Model Routing, Data Controls, and Cost

**Specification version:** 2.1  
**Primary owner:** AI platform  
**Audit date:** 2026-08-05

## Purpose

Provide one typed, audited OpenAI integration for Responses API calls, Structured Outputs, web search, long-form/background research, webhooks, usage/cost accounting, retention/data controls, and policy-based model routing.

## Architecture decision

Business services MUST NOT instantiate the OpenAI SDK. They call a typed provider adapter. PostgreSQL/Celery own workflow state. The OpenAI Agents SDK may be evaluated for isolated experiments, but it cannot become the canonical orchestrator without a new ADR.

## Adapter interface

```python
T = TypeVar("T", bound=BaseModel)

class OpenAIProvider(Protocol):
    def structured_response(self, request: StructuredRequest[T]) -> ProviderResult[T]: ...
    def web_research(self, request: WebResearchRequest) -> WebResearchResult: ...
    def start_background_research(self, request: ExtendedResearchRequest) -> BackgroundResponseRef: ...
    def retrieve_response(self, response_id: str) -> RetrievedResponse: ...
    def cancel_response(self, response_id: str) -> None: ...
    def verify_webhook(self, raw_body: bytes, headers: Mapping[str, str]) -> VerifiedWebhookEvent: ...
    def smoke_test_capability(self, policy: ModelPolicy) -> CapabilityTestResult: ...
```

## Current seed policies

These are reviewed seed defaults, not permanent business constants:

| Workload | Seed model policy | Reasoning | Tools |
|---|---|---|---|
| high-volume extraction/classification | `gpt-5.6-luna` | low | none |
| standard public company research | `gpt-5.6-terra` | medium/high after eval | current `web_search` |
| solution design/drafting/critic | `gpt-5.6-terra` | medium after eval | none |
| difficult premium reasoning | `gpt-5.6-sol` | evaluated | none or approved current tools |
| selective extended/deep research | current `gpt-5.6-terra` or `gpt-5.6-sol` policy | high/xhigh after eval | current `web_search`, background where supported |

Dedicated `o3-deep-research` and `o4-mini-deep-research` policies are marked legacy/deprecated and disabled by default. They may be enabled only when current official docs/account capability, smoke tests, and FTL evaluations confirm they remain available and beneficial.

## ModelCapability

```json
{
  "model": "gpt-5.6-terra",
  "status": "active|legacy|deprecated|disabled",
  "supports_responses": true,
  "supports_structured_outputs": true,
  "supports_web_search": true,
  "web_search_tool_type": "web_search",
  "supports_source_list_include": true,
  "supports_background": true,
  "supports_background_store_false": true,
  "supports_reasoning_effort": true,
  "allowed_reasoning_efforts": ["none", "low", "medium", "high", "xhigh", "max"],
  "supports_store_false": true,
  "maximum_tool_calls": null,
  "effective_from": "2026-08-05",
  "last_smoke_test_at": null,
  "official_reference_snapshot": "..."
}
```

The adapter filters parameters through this registry. Unsupported temperature, reasoning, tool, include, storage, or output parameters are never passed blindly.

## Structured Outputs

Use the current official Python Responses pattern, verified against the installed SDK:

```python
response = client.responses.parse(
    model=policy.model,
    instructions=developer_prompt,
    input=[{"role": "user", "content": user_prompt}],
    text_format=OutputModel,
    **capability_filtered_parameters,
)
parsed = response.output_parsed
```

Every schema uses Pydantic v2 with strict enums/bounds and `extra="forbid"` where supported by the schema strategy.

The adapter handles explicitly:

```text
provider refusal
status=incomplete and incomplete reason
no usable message/output
schema parse failure
invalid catalog/reference IDs
rate limit/timeout/provider error
budget/policy block
model/tool capability mismatch
```

Do not use regex or generic JSON repair as the normal path. At most one stage-approved bounded repair attempt may receive the validation errors and original output; it may not add evidence.

## Prompt construction

- Trusted static developer instructions first.
- Dynamic source/report/email text in delimited user data only.
- Never interpolate untrusted content into developer instructions.
- Keep stable prompt prefixes byte-identical where practical for caching.
- Record prompt/template/input hashes and versions, never secrets.
- Do not request/store hidden chain-of-thought; request concise rationale, evidence IDs, uncertainties, and review flags instead.

## Standard web research

Use a current web-search-capable Responses model and current `web_search` tool. Preserve:

```text
provider response ID
output/report text
URL citation annotations and locations
cited URL/title metadata
complete consulted-source list when supported by the current include/source field
web-search call metadata
retrieval time
brief/prompt/model/tool/data-control policy
usage/cost
```

Python assigns local source IDs from provider metadata. A separate no-web Structured Output call creates canonical claims. URLs written only in model prose are not accepted as sources.

## Extended / deep research

Default to an evaluated current general reasoning policy with `web_search`. Use:

- `background=true` when supported/useful;
- explicit `max_tool_calls`, output, source, budget, and concurrency limits;
- immediate persistence of provider response ID;
- verified webhook notification plus polling recovery;
- prompt/report/source persistence and a separate no-web extractor;
- no arbitrary application write/function tools;
- no private FTL knowledge or CRM data.

Legacy dedicated deep-research model policies remain opt-in and capability-tested only.

## Background Mode, `store`, and ZDR

Current OpenAI documentation allows Background Mode with `store=false` for Zero Data Retention projects while temporary response state is retained for a short documented polling/retrieval window (currently approximately ten minutes). Treat this as a fast-changing provider capability:

- model/data-control policy declares support;
- implementation smoke-tests the combination;
- terminal output is retrieved promptly;
- a stricter client policy may disable background despite provider ZDR support;
- persist `background`, `store`, ZDR/project policy, and retrieval timestamps;
- do not describe all background calls as incompatible with ZDR.

For eligible non-background calls, default to `store=false` unless a reviewed provider-retention purpose exists.

## Webhooks

Use the current official SDK signature-verification helper (currently the `client.webhooks.unwrap(...)` family or documented equivalent) on the raw body and headers. Requirements:

- reject before business parsing on invalid signature;
- deduplicate provider webhook/event ID;
- allowlist event types;
- map response ID to an existing run;
- enqueue retrieval through the outbox;
- retrieve the canonical response by ID before updating research output;
- return quickly.

## ProviderCall and usage

Record:

```text
provider and operation
model/capability/prompt/schema/policy versions
input object IDs and canonical input hash
provider request/response ID
status and redacted error code/message
start/end/duration
input/output/cached/reasoning tokens where returned
tool-call and source counts
estimated/actual cost and pricing-policy version
retry count
background/store/data-control flags
webhook/poll provenance
```

Never store authorization headers or secret values.

## Cost and rate controls

- daily/monthly account and stage budgets;
- per-run tool/source/output limits;
- per-model and per-stage concurrency;
- manual authorization above threshold;
- duplicate input/brief-hash prevention;
- provider rate-limit-aware retry and circuit breaker;
- cost dashboard and alerts;
- optional calls fail closed when budget is exhausted while core UI remains available.

## Batch processing

The Batch API MAY later handle non-urgent high-volume classification after synchronous contracts and local evaluations are stable. Every batch item maps to a stored input hash/idempotency key. Batch state never replaces domain state.

## Capability verification

At lock-file creation and every model/tool upgrade:

1. consult current official references in file `31`;
2. verify installed SDK signature;
3. run mocked contract tests;
4. run a minimal opt-in live smoke test for each enabled capability;
5. run FTL evaluation fixtures;
6. record date/result in `ModelCapability`/`DECISIONS.md`;
7. activate the immutable policy only after human review.

## Acceptance criteria

- Every OpenAI call goes through one adapter and creates a provider-call record.
- Business services contain no model IDs or provider-specific tool syntax.
- Structured output fails closed on refusal/incomplete/schema/reference error.
- Research preserves provider citations/source metadata and uses a no-web extractor.
- Extended research uses current policies; deprecated dedicated policies are disabled by default.
- Background/store/ZDR behavior is explicit, current, and tested.
- Webhook verification and deduplication are covered by tests.
- Costs, retention flags, and model/prompt/schema provenance are queryable.
