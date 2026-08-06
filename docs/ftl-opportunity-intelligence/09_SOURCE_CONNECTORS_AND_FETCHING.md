# 09 — Source Connectors and Safe Fetching

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Ingestion  
**Audience:** Codex and FTL engineers

## 1. Purpose

Define provider adapters, safe HTTP retrieval, parser precedence, provenance, source-policy enforcement, and browser isolation.

## 2. Connector boundary

```python
class SourceConnector(Protocol):
    key: str
    version: str

    def can_handle(self, candidate: SourceCandidateDTO) -> bool: ...
    def discover_items(self, endpoint: SourceEndpointDTO) -> list[SourceItemRefDTO]: ...
    def parse_snapshot(self, snapshot: SourceSnapshotDTO) -> ParsedPostingDTO: ...
```

Retrieval is centralized in a safe fetch service. Connector code MUST NOT create arbitrary `httpx` clients or bypass network policy.

## 3. Required connectors

Initial:

```text
Personio
Greenhouse
JobPosting JSON-LD
generic static HTML
```

Next:

```text
Lever
Ashby
sitemap/career index
optional Playwright-rendered page
```

Provider-specific connectors use documented public feeds/APIs where available. Generic HTML/Playwright is a fallback.

Parser precedence:

```text
public provider API/feed
    -> JobPosting JSON-LD
    -> deterministic static HTML rules
    -> isolated Playwright
    -> explicitly approved model-assisted extraction fallback
```

Model-assisted extraction is never the default and still requires persisted source text plus strict schema validation.

## 4. Safe fetch request

```json
{
  "source_endpoint_id": "uuid",
  "requested_url": "https://...",
  "method": "GET",
  "conditional_headers": {
    "if_none_match": null,
    "if_modified_since": null
  },
  "policy_key": "public_job_page",
  "max_response_bytes": 10485760,
  "idempotency_key": "..."
}
```

## 5. FetchResult

```json
{
  "schema_version": "2.0",
  "requested_url": "https://...",
  "final_url": "https://...",
  "status_code": 200,
  "retrieved_at": "2026-08-05T08:00:00Z",
  "content_type": "text/html",
  "encoding": "utf-8",
  "headers_filtered": {
    "etag": "...",
    "last-modified": "...",
    "content-language": "de"
  },
  "body_sha256": "...",
  "body_size_bytes": 123456,
  "elapsed_ms": 431,
  "redirect_chain": [],
  "network_policy": "allowed",
  "robots_policy": "allowed|unknown|blocked|not_applicable",
  "warnings": []
}
```

The raw body is persisted separately and is not returned through general operations APIs.

## 6. SSRF and network policy

The fetch service MUST:

1. parse and normalize the URL;
2. permit only configured schemes, normally HTTPS;
3. reject userinfo and unsupported ports;
4. resolve DNS through a controlled resolver path;
5. reject every resolved loopback, private, link-local, carrier-grade NAT, multicast, unspecified, reserved, and cloud-metadata address;
6. connect only to the validated address/host relationship where the HTTP stack permits safe control;
7. revalidate every redirect target before following it;
8. limit redirects;
9. protect against DNS rebinding by not trusting a prior string-only validation;
10. block hostnames and CIDRs from policy deny lists;
11. prevent access to Docker/internal service names;
12. record a safe rejection reason.

Tests must cover IPv4, IPv6, decimal/octal/hex representations where parsers accept them, IDNA, mixed DNS results, redirects to private targets, and metadata endpoints.

## 7. HTTP behavior

Use one configured `httpx` client/factory with:

- separate connect/read/write/pool timeouts;
- total task deadline;
- bounded response size, including decompressed size;
- streaming body read;
- conditional requests through ETag/Last-Modified;
- descriptive contactable user agent;
- per-domain concurrency and rate limits;
- retry only for safe idempotent methods and transient failures;
- `Retry-After` support;
- TLS verification enabled;
- no ambient proxy credentials unless explicitly configured;
- filtered response headers;
- no cookie persistence across unrelated sites.

Do not retry 400/401/403/404/410 by default. A 429 or selected 5xx can be retried with bounded exponential backoff and jitter.

## 8. Robots, terms, and source policy

- Record robots outcome where applicable.
- Do not bypass technical access controls.
- Do not crawl authenticated/gated pages.
- Do not scrape private professional networks such as authenticated LinkedIn pages.
- Respect provider/API terms and rate limits.
- Prefer public first-party feeds.
- Allow a human to block a domain/source globally.

Robots policy is one source-policy input, not the sole legal determination. Blocked sources remain visible in operations with no body retrieval.

## 9. SourceEndpoint

Required fields include:

```text
provider_type
base_url_original/canonical
tenant_key
company_id nullable
connector_key/version
configuration JSONB
status
robots_policy
rate_policy_key
etag/last_modified
last_success/failure
consecutive_failures
next_allowed_fetch_at
last_schema_change_at
```

A source may be `degraded` after repeated parse/fetch failures but must not be archived automatically without policy.

## 10. Fetch attempts and snapshots

Every request creates `FetchAttempt`.

- `304 Not Modified`: attempt only, no duplicate content snapshot.
- identical body hash after 200: attempt and observation; no duplicate `SourceSnapshot` unless policy needs header history.
- changed body: immutable snapshot.
- blocked/unsafe: attempt with no body.
- failed: attempt with safe error metadata.

This separation makes source health and posting absence measurable without duplicating content.

## 11. Provider adapters

### 11.1 Personio

- discover public XML/feed endpoint from configured tenant;
- preserve provider position ID;
- parse office, department, recruiting category, schedule, descriptions, and URLs;
- fixture-test namespace and optional-field variations.

### 11.2 Greenhouse

- use public job-board endpoints where available;
- preserve job ID and board token;
- support pagination/departments/offices;
- treat provider HTML fields as untrusted and sanitize for display.

### 11.3 Lever and Ashby

- use public posting interfaces where documented;
- preserve provider identity and canonical hosted-job URL;
- test pagination and closed-posting behavior.

### 11.4 JSON-LD

- extract all scripts safely without executing them;
- handle arrays/graphs;
- select `JobPosting` objects;
- preserve raw JSON-LD object;
- validate dates and organization/location structures;
- do not trust structured data as proof of company identity without source context.

### 11.5 Generic HTML

- rules are domain/provider scoped where possible;
- text extraction preserves headings and list items;
- scripts/styles/navigation boilerplate excluded deterministically;
- selector breakage creates a visible parse failure.

## 12. Playwright

Run only in a separate worker/service/profile.

Controls:

```text
no persistent browser profile
no downloads
no extension loading
JavaScript allowed only for the target page
block unnecessary third-party resources where possible
bounded navigation/total timeout
bounded page/context count
memory/CPU limits
same SSRF/redirect policy
no access to application secrets or internal network
sanitized screenshot/HTML diagnostics only when retention permits
```

A browser timeout does not cause the source to be treated as closed.

## 13. Parsed posting output

```json
{
  "schema_version": "2.0",
  "connector_key": "greenhouse",
  "connector_version": "1.1.0",
  "source_snapshot_id": "uuid",
  "provider_external_id": "12345",
  "canonical_url": "https://...",
  "company_name": "Example",
  "company_domain_hint": "example.com",
  "title": "AI Content Producer",
  "department": "Marketing",
  "employment_type": "full_time",
  "seniority": null,
  "locations": [
    {"label": "Munich", "country_code": "DE", "remote": false, "confidence": 0.98}
  ],
  "published_at": null,
  "valid_through": null,
  "description_text": "...",
  "description_html_sanitized": "...",
  "language": "en",
  "field_provenance": {
    "title": {"source_path": "jobs[0].title", "method": "provider_api"}
  },
  "warnings": []
}
```

## 14. Tests

- provider fixtures for normal, missing, malformed, paginated, and closed jobs;
- JSON-LD arrays/graphs and invalid dates;
- conditional GET and 304;
- response-size and decompression limit;
- redirect-chain SSRF;
- DNS rebinding-oriented validation;
- per-domain throttling;
- retry/no-retry matrix;
- first-party provenance;
- Playwright isolation and disabled behavior;
- raw payload never rendered unsanitized.

## 15. Acceptance criteria

- All connectors produce the same strict normalized boundary.
- Unsafe targets cannot be reached through redirects or alternate address forms.
- Fetch attempts remain visible independently of snapshots.
- Source failures do not create posting closure.
- One failed item does not discard successful batch items.
- No connector assigns FTL relevance or commercial interpretation.
