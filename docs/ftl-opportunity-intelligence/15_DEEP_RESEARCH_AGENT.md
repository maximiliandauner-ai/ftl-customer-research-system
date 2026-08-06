# 15 — Selective Extended / Deep Research Agent

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Research and AI platform  
**Canonical prompts:** `deep_research_brief_builder`, `deep_researcher`, `deep_research_extractor` version `2.1.0`

## 1. Purpose

Run long-form public research only when standard research leaves questions whose resolution could materially change qualification, solution design, infrastructure choice, governance, contact ownership, or proposal preparation.

This stage is selective. It is not the daily discovery mechanism and it must not run for every relevant job posting.

## 2. Trigger policy

A run requires all configured gates:

```text
opportunity qualified or manually selected
standard research complete or explicitly waived
critical unresolved questions recorded
company identity sufficiently resolved
estimated cost within policy
concurrency slot available
human authorization where threshold requires it
provider capability smoke test current
retention/data-control policy compatible
no duplicate active run for the same brief hash
```

Automatic triggers remain disabled until FTL has measured cost and value on reviewed cases.

## 3. Provider strategy as of the audit date

The default production policy SHOULD use a current general reasoning model evaluated for long-form research, such as the current GPT-5.6 Terra or Sol policy, with the current `web_search` tool, high/xhigh reasoning where supported, explicit tool-call limits, and Background Mode where useful.

Older dedicated `o3-deep-research` and `o4-mini-deep-research` model policies are legacy-compatible options only. Current model catalog documentation marks them as deprecated even though dedicated deep-research guidance may still describe them. They MUST be disabled by default and used only when the current account, official documentation, capability registry, and live smoke test all confirm support and an evaluation shows a benefit.

No business service hardcodes a model ID. `ModelPolicy` and `ModelCapability` determine:

```text
model ID and status
Responses API support
web-search tool shape
Structured Output support for the extractor
background support
store=false/ZDR behavior
reasoning-effort values
maximum tool calls/output
source-list include support
legacy/deprecation state
last smoke-test date
```

Research models receive read-only public-research tools only. They never receive arbitrary application write functions.

## 4. DeepResearchBriefV2

```json
{
  "schema_version": "2.1",
  "prompt_version": "2.1.0",
  "objective": "Resolve the organizational, infrastructure, and ownership-context questions that determine whether an internal AI content capability is a credible FTL opportunity.",
  "research_questions": [],
  "known_claim_ids": [],
  "critical_unknowns": [],
  "disconfirming_questions": [],
  "source_priority": [
    "official_company",
    "official_report",
    "official_registry",
    "reputable_press"
  ],
  "freshness_requirements": {},
  "allowed_domains": [],
  "blocked_domains": [],
  "maximum_tool_calls": 40,
  "maximum_sources": 60,
  "maximum_output_tokens": 16000,
  "required_sections": [],
  "explicit_exclusions": [
    "private FTL knowledge",
    "CRM records",
    "invented people or emails",
    "outreach copy"
  ]
}
```

The brief is created in a no-web Structured Output call and validated before research starts.

## 5. Asynchronous execution

```text
create immutable brief and brief hash
    -> reserve budget/concurrency atomically
    -> create ResearchRun + ProviderCall
    -> start Responses API request
    -> persist provider response ID immediately
    -> commit status=waiting_for_provider
    -> release worker
    -> verified webhook marks terminal notification
    -> polling fallback retrieves by response ID
    -> persist terminal report/citations/sources promptly
    -> local source registry
    -> no-web ResearchExtractionV2
    -> validation and canonical persistence
```

A worker never remains blocked for the entire provider research duration. Webhooks are notifications, not canonical output; the application retrieves the response by ID before persisting results.

## 6. Background Mode, `store`, and Zero Data Retention

Use `background=true` when the selected model/policy supports it and asynchronous execution adds value.

Current OpenAI documentation allows Background Mode in Zero Data Retention projects with `store=false`, while retaining temporary server-side state for a short documented window (currently approximately ten minutes) so the response can be polled/retrieved. This behavior is provider-specific and MUST be reverified at implementation and policy-review time.

Therefore:

- `background=true` does not automatically imply `store=true`;
- ZDR compatibility is a capability/policy field, not a hardcoded prohibition;
- retrieve and persist terminal output promptly;
- if FTL/client policy forbids even temporary provider-side processing state, use a compatible bounded synchronous path or disable the run;
- record `background`, `store`, data-control policy, and retrieval timestamps on `ProviderCall`.

## 7. Research output

The sourced report follows the approved brief and normally includes:

```text
Executive Summary
Verified Company and Initiative Context
Observed Capability Need
Organizational Ownership Context
External-Partner / Procurement Signals
Infrastructure, Privacy, and Governance Context
Long-Term System Potential
Evidence Against the Opportunity
Conflicts and Material Unknowns
Source Notes
```

It does not select final buyer roles, people, contact routes, FTL assets, or outreach language.

## 8. Source registration and extraction

Use the same two-pass contract as standard research:

1. persist report, native citations, provider source list, usage, and response provenance;
2. Python registers canonical `ResearchSource` records and stable source IDs;
3. a no-web extractor creates `ResearchExtractionV2` claims referencing only those IDs;
4. validate facts/inferences/hypotheses/conflicts/currentness before persistence.

A valid expensive report must not be discarded because a cheaper extractor fails. Extraction retry reuses the persisted report and source registry.

## 9. Webhook security and deduplication

The webhook endpoint MUST:

- receive the raw request body;
- verify signature using the current official SDK helper and configured webhook secret;
- reject invalid signatures before parsing business fields;
- persist/deduplicate the provider webhook/event ID;
- accept only configured event types;
- match the response ID to an existing run;
- enqueue a retrieve command through the transactional outbox;
- return quickly without performing research extraction inline.

Polling remains a recovery path for lost/delayed webhooks.

## 10. Cost and concurrency

Store and enforce:

```text
estimated maximum cost
actual token/tool/source usage
per-stage and per-opportunity budget
maximum concurrent extended-research runs
manual authorization threshold
maximum tool calls and output
brief-hash duplicate prevention
```

Budget exhaustion fails closed while leaving the dashboard usable.

## 11. Statuses

```text
draft
authorization_required
queued
starting
waiting_for_provider
retrieving
source_complete
extracting
complete
partial
review_required
failed
expired
canceled
stale
```

Representative failure codes:

```text
MODEL_POLICY_UNAVAILABLE
MODEL_POLICY_DEPRECATED
CAPABILITY_SMOKE_TEST_STALE
BUDGET_BLOCKED
PROVIDER_REFUSAL
PROVIDER_INCOMPLETE
PROVIDER_START_FAILED
BACKGROUND_RESPONSE_EXPIRED
WEBHOOK_SIGNATURE_INVALID
WEBHOOK_EVENT_DUPLICATE
RETRIEVAL_FAILED
REPORT_WITHOUT_REGISTERED_SOURCES
EXTRACTION_SCHEMA_INVALID
EXTRACTION_REFERENCE_INVALID
DATA_CONTROL_INCOMPATIBLE
```

## 12. Cancellation and retry

- canonical cancellation is a PostgreSQL request state;
- request provider cancellation where supported;
- Celery revoke is operational only;
- start requests are idempotent by brief/policy hash;
- a failed poll never starts a second provider run;
- retry start only when no provider response ID was persisted;
- retry retrieve/extract independently.

## 13. Dashboard

Show:

- brief and unresolved questions;
- authorization/budget/concurrency state;
- selected model/tool/background/store/data-control policy;
- provider response ID and current status;
- tool/source/token/cost usage;
- report, citations, source registry, claims, conflicts, and unknowns;
- webhook/poll history;
- retry retrieve, retry extract, cancel, and mark stale actions.

## 14. Tests

- default current general-reasoning research policy;
- deprecated dedicated model policy rejected unless explicitly enabled and smoke-tested;
- `background=true, store=false` capability path;
- stricter policy that disables temporary provider state;
- provider response ID persisted before worker release;
- valid/invalid/duplicate webhooks;
- webhook-lost polling recovery;
- response-expiry handling;
- duplicate brief hash does not start twice;
- expensive report survives extractor failure;
- private FTL data absent from request;
- model-written unsupported source rejected.

## 15. Acceptance criteria

- Model selection is capability-driven and reverified, not frozen in business code.
- Current web-search-based extended research is the default; deprecated dedicated models are opt-in legacy policies only.
- Long provider execution does not occupy a worker.
- Background/store/ZDR behavior is explicit and testable.
- Every persisted canonical claim references a registered source.
- The stage produces public evidence only; solution, asset, buyer-role, contact, and outreach stages remain separate.
