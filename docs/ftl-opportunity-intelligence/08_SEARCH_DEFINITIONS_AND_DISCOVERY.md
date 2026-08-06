# 08 — Search Definitions and Discovery Orchestrator

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Discovery  
**Audience:** Codex and FTL engineers

## 1. Purpose

Implement configurable, recurring discovery that finds candidate source URLs and known ATS endpoints. Discovery does not create evidence, signals, contacts, or opportunities.

## 2. Problem to solve

FTL wants broad early-stage coverage of organizations hiring for relevant creative, learning, automation, infrastructure, and enablement capabilities. Generic title searches alone have low recall; unrestricted web scraping creates noise and provenance problems.

The discovery layer therefore combines:

- versioned search definitions;
- recurring polling of known first-party endpoints;
- web-search candidate discovery;
- ATS-tenant identification;
- watched-company career monitoring;
- manual URL/domain submission;
- measurable query performance.

## 3. SearchDefinition

```json
{
  "schema_version": "2.0",
  "id": "uuid",
  "name": "German AI learning and creative production roles",
  "description": "Find first-party job pages revealing demand for AI-assisted learning, video, creative automation, or enablement.",
  "query_template": "{{role_terms}} {{capability_terms}} {{location_terms}}",
  "language": "de",
  "countries": ["DE", "AT", "CH"],
  "locations": ["Munich", "Remote"],
  "capability_clusters": [
    "learning_content",
    "creative_ai_production",
    "workflow_automation",
    "internal_enablement"
  ],
  "positive_terms": ["generative KI", "Lerncontent", "Videoproduktion"],
  "negative_terms": ["medical imaging", "quant trading"],
  "preferred_domains": [],
  "excluded_domains": [],
  "source_type_filters": ["job_posting", "career_page"],
  "schedule_key": "daily_morning",
  "active": true,
  "max_candidates": 50,
  "lookback_days": 21,
  "version": 1
}
```

Definitions are immutable by version. Editing creates a new version while historical runs retain the old payload/hash.

## 4. Discovery modes

### 4.1 Known endpoint polling

Preferred for companies already mapped to Personio, Greenhouse, Lever, Ashby, or a supported feed.

Output: source-item references to fetch. No LLM required.

### 4.2 Web-search discovery

Use the OpenAI Responses API web-search adapter or another approved search provider to find new candidate URLs.

The provider call MUST:

- use a bounded tool/candidate budget;
- use current web-search tool syntax verified at implementation time;
- request the complete returned source list when needed;
- store provider call provenance;
- prefer first-party career/ATS domains;
- return candidate URLs, not canonical facts;
- not mix private FTL knowledge into public search.

### 4.3 Watched-company career discovery

For selected companies:

- inspect registered career endpoints;
- inspect allowed sitemap/robots metadata;
- discover ATS tenant links;
- create new `SourceEndpoint` candidates;
- schedule bounded polling.

### 4.4 Manual submission

A user may submit a URL or domain. It enters the same safety, canonicalization, fetch, parse, and review pipeline. Manual input does not bypass SSRF/source policy.

## 5. Input

```json
{
  "search_definition_id": "uuid",
  "logical_window_start": "2026-08-04T06:00:00Z",
  "logical_window_end": "2026-08-05T06:00:00Z",
  "run_reason": "scheduled",
  "known_url_hashes": ["sha256"],
  "budget": {
    "max_tool_calls": 8,
    "max_candidates": 50,
    "max_provider_cost_usd": 0.50
  }
}
```

## 6. Candidate output

```json
{
  "schema_version": "2.0",
  "discovery_run_id": "uuid",
  "candidates": [
    {
      "url": "https://company.jobs.personio.de/job/12345",
      "title_hint": "Werkstudent Videoproduktion und KI-Content",
      "company_hint": "Example Company",
      "company_domain_hint": "example.com",
      "source_type_hint": "personio",
      "location_hints": ["Munich"],
      "matched_terms": ["KI-Content", "Videoproduktion"],
      "snippet_hint": "Search-result snippet retained only for discovery diagnostics.",
      "candidate_confidence": 0.82,
      "provider_source_reference": "provider-specific-id|null"
    }
  ],
  "queries_executed": [],
  "warnings": [],
  "partial": false
}
```

`snippet_hint` MUST NOT become evidence or be quoted in an opportunity. Evidence exists only after a source is fetched and persisted.

## 7. Query families

Search definitions should combine title, task, tooling, organizational, and infrastructure language.

### Creative production

```text
AI Video Producer
Generative AI Content
Creative Technologist AI video
KI Videoproduktion Karriere
Runway Kling ComfyUI job
synthetic media producer
```

### Learning and enablement

```text
AI learning content
Digital Learning generative AI
KI Lerncontent
AI academy content
AI enablement workshop jobs
instructional design generative AI
```

### Workflow and infrastructure

```text
AI workflow automation internal tools
local LLM internal platform
private AI on premises
AI knowledge management automation
meeting minutes AI workflow
ticket classification AI
```

### Task-level matching

Generate query variants around responsibilities, not only role titles:

```text
develop reusable prompt templates
create AI-generated learning videos
evaluate generative video tools
build internal AI workflows
train employees in generative AI
deploy models on internal GPU infrastructure
```

## 8. Candidate canonicalization

Before persistence:

1. require `http`/`https`, with HTTP allowed only by explicit local/source policy;
2. normalize scheme and IDNA hostname;
3. remove fragment;
4. remove only known tracking parameters;
5. preserve functional and signed query parameters;
6. reject userinfo, unsupported ports, malformed hosts, and unsafe destinations;
7. compute URL hash;
8. compare existing candidates/endpoints/snapshots;
9. group by registrable domain and ATS provider hint.

Do not fetch during URL string canonicalization. Network safety resolution occurs in the fetching layer.

## 9. Scheduling and leases

Default schedule: once daily in `Europe/Berlin`; store logical UTC windows.

The scheduler creates one `DiscoveryRun` per `(definition version, logical window)`. A unique idempotency key and database lease prevent duplicate execution when Beat or workers restart.

Manual runs use a different run reason and explicit force policy but still deduplicate candidate URLs.

## 10. Performance metrics

Per definition/version:

```text
runs
successful_runs
partial_runs
provider_cost
queries/tool_calls
candidates_found
first_party_candidate_rate
unsafe_candidate_rate
new_endpoint_rate
fetch_success_rate
parse_success_rate
relevant_signal_rate
qualified_opportunity_rate
precision_at_reviewed_k
last_success_at
```

Definitions with repeated zero yield or high noise should be reviewed, not silently expanded by the model.

## 11. Failure behavior

- One query failure produces a partial run, not loss of successful candidates.
- Authentication/quota failure disables only the affected provider path and alerts operations.
- Unsafe URLs are stored with a safe rejection reason but are not fetched.
- Candidate results remain inspectable.
- Search provider output failing strict schema validation is retried at most once, then marked failed.
- A failed discovery run never closes existing postings.

## 12. Dashboard

### `/discovery/definitions/`

Show active definitions, version, schedule, last run, yield, qualified rate, cost, and health.

### `/discovery/runs/<id>/`

Show queries, provider calls, candidates, rejected unsafe URLs, first-party ratio, warnings, and downstream fetch state.

### `/discovery/candidates/`

Filter by status, domain, source hint, definition, date, and rejection reason. Allow safe manual requeue or endpoint registration.

## 13. Tests

- logical-window idempotency;
- query-definition versioning;
- candidate strict schema;
- snippet never enters evidence tables;
- URL canonicalization preserves functional parameters;
- unsafe schemes/hosts rejected;
- partial provider failure;
- candidate duplicate behavior;
- manual and scheduled paths share services;
- cost/metric attribution.

## 14. Acceptance criteria

- Daily runs are reproducible and inspectable.
- Discovery creates only candidates/endpoints, never signals/opportunities.
- Every candidate retains provider/run provenance.
- Search snippets cannot become canonical evidence.
- Known endpoints are polled deterministically without repeated web rediscovery.
- Query performance can be compared by version.
