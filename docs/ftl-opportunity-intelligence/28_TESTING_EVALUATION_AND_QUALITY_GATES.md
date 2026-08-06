# 28 — Testing, Evaluation, and Quality Gates

**Specification version:** 2.1  
**Primary owner:** Quality engineering

## Purpose

Define deterministic software tests, connector contracts, local AI evaluations, adversarial safety cases, end-to-end scenarios, performance assertions, migration/restore tests, and prompt/model release gates.

## Tooling baseline

```text
pytest
pytest-django
pytest-xdist where stable
ruff
mypy + django-stubs
respx for HTTPX
freezegun or time-machine
hypothesis for canonicalization/state invariants
Playwright for browser E2E
coverage.py
```

No test or CI job requires production secrets. Live-provider smoke tests are opt-in and separately budgeted.

## Test pyramid

### Unit

- URL/domain normalization;
- SSRF address/redirect validation;
- text/section normalization;
- hashes and packet canonical JSON;
- scoring weights/ranges;
- state transitions/approval invalidation;
- outbox idempotency/retry policy;
- Pydantic schemas/enums;
- redaction;
- prompt rendering and input separation.

### Contract

- Personio/Greenhouse/Lever/Ashby fixture responses;
- JSON-LD and generic HTML variants;
- OpenAI structured, refusal, incomplete, citation, background, and webhook mocked shapes;
- email provider draft rendering;
- storage backend;
- schema backward compatibility.

### Integration

- ORM constraints/concurrency;
- database transaction + outbox publication gap recovery;
- Celery eager and real broker modes;
- source -> posting -> snapshot -> signal -> assessment;
- research source normalization/extraction;
- packet -> structured draft units -> deterministic rendering/review;
- suppression cascade;
- backup/restore into clean database;
- migrations from previous release tag.

### End to end

```text
login
  -> submit/discover HOFFMANN-EITLE-like URL
  -> inspect posting/snapshot/source
  -> signal/evidence/classification
  -> qualify company/opportunity
  -> standard research and sources
  -> solution design/approval
  -> buyer role and route selection
  -> packet and source-bound draft
  -> factual review
  -> human approval
  -> optional external provider draft
  -> interaction/reply/suppression
```

## AI evaluation dataset

Keep a local versioned dataset under `tests/evals/` or `evaluation/`. Do not make provider-hosted Evals the canonical harness. OpenAI currently documents the legacy Evals API as read-only after October 31, 2026 and shut down after November 30, 2026. Keep fixtures, labels, comparisons, and release decisions locally; newer provider dataset/evaluation tooling may be an optional adapter.

Required cases:

```text
strong creative AI production
learning content and internal pipeline
workflow automation
local/private AI
Create-only production
Create-Build-Enable system
hybrid employee plus external partner
employment-only
unrelated AI engineering
stale/closed role
ambiguous evidence
multi-role company pattern
prompt injection in job description
prompt injection in web page
malicious citation/source ID
prompt injection in inbound email
confidential asset exclusion
unsupported local-AI assumption
```

## Ground truth

For each case:

```text
relevant yes/no
allowed capability clusters/gaps
valid evidence spans
opportunity mode
allowed FTL layers/entry offers
component score ranges
infrastructure expectation
expected unknowns/flags
forbidden claims
accepted solution characteristics
accepted draft characteristics
```

## AI metrics

- precision@K for reviewed leads;
- false-positive rate;
- evidence exact-match validity;
- schema/refusal/incomplete rate;
- capability-gap agreement;
- opportunity-mode agreement;
- score calibration/routing agreement;
- research citation completeness and source validity;
- source hallucination count (target zero);
- solution human acceptance/revision rate;
- draft content-unit binding completeness;
- unsupported claim rate (release blocker);
- cost/latency per accepted result.

## Prompt/model release gate

```text
create candidate prompt/model policy
  -> run full deterministic and AI eval suite
  -> compare against active baseline
  -> inspect regressions by category
  -> human approval
  -> activate immutable new version
  -> monitor production sample
  -> retain rollback policy
```

A model alias update is treated as a model-policy change and requires evaluation.

## Prompt golden tests

- developer prompt static prefix hash;
- user template places all untrusted input only in data delimiters;
- no secret/private context in public research prompt;
- output model/schema matches registry metadata;
- prompt rendering contains no unresolved template token;
- prompt injection cannot appear in developer message.

## CI

```text
ruff format --check
ruff check
mypy
pytest -m "not live_provider"
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py check --deploy --settings=config.settings.production  # with safe CI settings
schema compatibility checks
Docker image build
selected Playwright E2E
```

## Performance and query quality

Representative dataset:

```text
10,000 postings
50,000 snapshots
5,000 signals
1,000 companies
```

Assert query counts and bounded response times for signal inbox, company detail, research claims/sources, contact routes, drafts, and Operations. Use indexes based on measured plans.

## Restore drill

CI or a scheduled local/server drill MUST:

1. create representative data;
2. produce a backup;
3. restore into a new empty PostgreSQL container/volume;
4. run migrations/verification;
5. compare critical counts/hashes;
6. smoke test login/read pages.

## Release blockers

- missing/unapplied migration;
- failing connector contract;
- unsupported-claim or source-hallucination regression;
- prompt-injection or SSRF failure;
- broken outbox recovery;
- approval/suppression bypass;
- backup restore failure;
- unversioned schema/prompt/model policy change;
- live API dependency in normal CI.

## Acceptance criteria

- One Docker command runs the default suite.
- AI eval reports preserve input/prompt/model/schema/policy versions.
- Critical path has E2E coverage.
- No production secret is needed.
- Restore and security tests are release gates.
