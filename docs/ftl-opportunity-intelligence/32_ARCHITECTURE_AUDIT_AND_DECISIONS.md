# 32 — Architecture and Prompt Audit: Binding Corrections

**Document status:** Binding architecture decision record  
**Specification version:** 2.1  
**Audit date:** 2026-08-05  
**Primary owner:** FTL engineering

## 1. Verdict

The original knowledge base had a strong product model and an appropriate local-first Python architecture, but it was not fully implementation-safe as written. The audited release corrects cross-document ordering conflicts, evidence/provenance gaps, Celery delivery semantics, deterministic hashing, current OpenAI research/data-control behavior, contact-route provenance, and outreach claim binding.

The resulting design is current and implementation-ready **as of the audit date**, subject to the explicit capability/version rechecks in file `31`. No prompt or provider integration is permanently “perfect”; every prompt/model/tool change requires local evaluation and human activation.

## 2. Audit scope

The review covered:

- FTL product and commercial semantics;
- Django/PostgreSQL/Celery/Docker architecture and portability;
- database normalization, migrations, audit, outbox, and idempotency;
- source discovery, safe fetching, evidence identity, and deduplication;
- narrow agent boundaries, schemas, prompt-injection defenses, and evaluations;
- OpenAI Responses API, Structured Outputs, web research, background execution, webhooks, data controls, and current model transition;
- contact provenance, suppression, drafting, and human approval;
- Codex repository instructions and long-running implementation workflow.

## 3. Corrected issues

| ID | Previous issue | Binding correction | Main files |
|---|---|---|---|
| A-001 | A job posting and an inferred company pattern could be represented as the same signal. | `SignalEvent` stores observable events only. Multi-signal interpretations use `CompanyPattern`/`CompanyAssessment`. | `01`, `11`, `13` |
| A-002 | Solution, asset, buyer-role, and contact ordering differed. | Research -> solution design -> asset matching -> buyer-role/public-or-human route discovery -> packet. Research preserves ownership context only. | `02`, `14`, `16`, `18`, `33` |
| A-003 | Employment-only, external-service, and hybrid values were modeled as overlapping probabilities. | Use one mutually exclusive `opportunity_mode` enum plus confidence/evidence; keep component scores separate. | `12`, `13`, `33` |
| A-004 | Packet hashing included volatile output identifiers/timestamps. | Hash a canonical stable-input manifest of immutable IDs, row versions, and content hashes; exclude packet ID/time/rendering fields. | `06`, `19` |
| A-005 | `transaction.on_commit(task.delay)` left a commit/publish failure window. | Use a transactional PostgreSQL outbox, an idempotent dispatcher, and idempotent tasks. | `02`, `06`, `24` |
| A-006 | Celery result state risked becoming a second source of truth. | Tasks normally ignore results and update durable PostgreSQL domain/run records. | `24`, `26` |
| A-007 | Public research and structured claims were mixed in one unbounded agent. | First produce a cited web report; then locally register sources; then run a no-web strict extractor referencing only registered IDs. | `14`, `15`, `25`, `33` |
| A-008 | Public browsing could receive private FTL knowledge. | Keep public research and private FTL solution/asset matching in separate trust boundaries. | `14`, `17`, `18`, `27` |
| A-009 | Research extraction could prematurely create buyer roles. | Research emits categorized `organizational_ownership` claims only; buyer-role inference follows solution design. | `14`, `16`, `33` |
| A-010 | Contact “verification” collapsed provenance, freshness, delivery, and permission. | Store route origin, observation, freshness, deliverability, eligibility, and recommendation separately. | `06`, `16`, `27` |
| A-011 | Public extraction could imply warm introductions or relationships. | Automated extraction creates `public_source` routes only. Warm introduction/existing relationship/event routes require authorized human provenance. | `06`, `16`, `33` |
| A-012 | Draft prose could not always be traced exactly to evidence. | Models author structured subject/body/short-message units with exact packet bindings; Python deterministically renders the message. | `06`, `20`, `21`, `33` |
| A-013 | Large HTML/research output was assumed to fit indefinitely in relational text fields. | Store large immutable artifacts through Django storage; PostgreSQL stores identity, hashes, policy, and references. | `02`, `06`, `29` |
| A-014 | PostgreSQL 18 used the historical Docker volume path in one example. | Mount the official PostgreSQL 18 volume at `/var/lib/postgresql`. | `04`, `29`, `31` |
| A-015 | Framework documents disagreed between Django 5.2 LTS and Django 6.0. | First implementation uses latest reviewed Django 5.2 LTS security patch; reassess 6.2 LTS through an ADR. | `README`, `04`, `31`, `34` |
| A-016 | Docker development proxy and direct Django server reused the same host port. | Proxy defaults to 8000; optional direct Django development server defaults to 8001. | `04` |
| A-017 | Incoming email was not consistently hostile input. | Deterministic unsubscribe/objection handling runs first; reply AI has no tools and cannot send/change suppression. | `22`, `27`, `33` |
| A-018 | Fetching needed stronger SSRF/redirect/DNS defenses. | Validate scheme/host/port/IP on every connection/redirect; reject prohibited networks; bound bytes/time/types. | `09`, `27` |
| A-019 | Background Mode was described as categorically incompatible with ZDR. | Current provider docs allow `background=true` with `store=false` for ZDR projects and a short temporary retrieval window; model this as a reverified policy capability. | `15`, `25`, `31` |
| A-020 | Deprecated dedicated deep-research models were hardcoded as defaults. | Default to evaluated current GPT-5.6 reasoning models plus `web_search`; legacy dedicated models are disabled unless current capability/eval gates pass. | `15`, `25`, `31` |
| A-021 | Provider-hosted evaluation lifecycle could become canonical. | Keep versioned fixtures/eval reports locally; legacy OpenAI Evals API transition dates are documented; provider tools are optional adapters. | `28`, `31` |
| A-022 | The Codex prompt duplicated specifications and referenced nonexistent files. | Use `AGENTS.md`, a lean map-based master prompt, one milestone at a time, durable `PLANS.md`/status/decisions, and executed verification. | `README`, `34`, `35` |

## 4. Binding architecture decisions

### ADR-001 — Modular monolith first

One Django codebase with bounded apps, PostgreSQL, Celery workers, Redis-compatible broker, and server-rendered HTMX UI. Microservices, Kafka, Kubernetes, and a separate SPA require measured justification.

### ADR-002 — Long-support baseline

Python 3.13, latest reviewed Django 5.2 LTS patch, PostgreSQL 18, Celery 5.6, and a current Redis-compatible broker. Patch/image/model changes are locked and tested; major changes require an ADR where material.

### ADR-003 — PostgreSQL is canonical

Domain state, audit, policies, outbox, approvals, and operational runs live in PostgreSQL. Redis and Celery messages are disposable transport.

### ADR-004 — Transactional outbox

A domain transaction writes the state change and outbox command together. Dispatcher publication and consumer effects are idempotent. This closes the database-commit/broker-publish gap.

### ADR-005 — Direct Responses API behind one adapter

The application owns orchestration and calls OpenAI through a typed provider adapter. Model/tool/data-control details live in versioned capability policies. The Agents SDK is optional for isolated experiments, not canonical workflow state.

### ADR-006 — Narrow agents with strict contracts

Retrieval, change classification, signal detection, capability assessment, research, solution design, asset matching, buyer-role inference, route extraction, drafting, review, and reply classification remain separate and independently testable.

### ADR-007 — Deterministic evidence catalog

Python creates source/evidence/claim IDs from persisted records. Models may reference supplied IDs only. Hallucinated URLs/IDs and unsupported references fail validation.

### ADR-008 — Two-pass research

A web-enabled call creates a cited public report. Python registers sources. A separate no-web call creates strict categorized claims. Buyer roles and FTL matching remain downstream.

### ADR-009 — Public/private separation

Public browsing never receives private FTL knowledge, CRM, contacts, or email history. Validated public claims are later combined with an approved FTL knowledge release without web access.

### ADR-010 — Solution before proof and target

The system first designs the smallest credible engagement. It then selects zero-to-two relevant public proof points and infers buyer roles/routes in relation to that solution.

### ADR-011 — Contact provenance model

Public-source routes and human-origin routes are different provenance classes. Observation, freshness, deliverability, eligibility, recommendation, and suppression are independent.

### ADR-012 — Structured outreach content

The model returns source-bound content units. Python deterministically renders plaintext/HTML. Human approval binds exact unit, rendering, packet, and route hashes.

### ADR-013 — Human-controlled outreach

The platform may create an external provider draft after exact-version approval and synchronous rechecks. It does not auto-send first contact in the initial product.

### ADR-014 — Portable artifact storage

Django storage owns large immutable source/report/export artifacts; PostgreSQL stores metadata/hashes. Local volumes can migrate to a server filesystem or S3-compatible backend without changing domain services.

### ADR-015 — Local evaluation harness

Versioned fixtures, labels, prompt/model-policy comparisons, and release gates live in the repository/database. Provider-hosted evaluation products may supplement but not replace them.

## 5. Prompt audit verdict

`33_AGENT_PROMPT_ENGINEERING_STANDARD.md` is now the canonical implementation contract. It requires:

- Pydantic v2 Structured Outputs with strict enums/bounds and forbidden extra fields;
- untrusted source text in user/data payloads only;
- facts, inferences, hypotheses, unknowns, conflicts, and counter-evidence kept distinct;
- supplied catalog IDs only;
- stage-specific tool permissions;
- explicit refusal, incomplete, schema, reference, provider, budget, and policy failures;
- at most one bounded repair where explicitly allowed;
- no hidden chain-of-thought requests;
- model/prompt/schema/capability provenance;
- public/private context separation;
- categorized research claims rather than premature buyer roles;
- structured draft content units and exact bindings;
- no agent approval, suppression override, or send action;
- local fixtures and activation gates for every prompt/model-policy release.

The prompts are ready to implement as versioned contracts. They still require model-specific evaluation before activation.

## 6. Upgrade triggers

Create/update an ADR before changing:

- framework/database/broker major series;
- canonical workflow engine;
- evidence/source identity scheme;
- public/private research boundary;
- contact provenance/encryption model;
- external sending policy;
- production model family/tool type/data-control behavior;
- storage backend semantics;
- a provider/agent framework becoming canonical orchestration state owner.

## 7. Audit acceptance criteria

- all local Markdown references resolve;
- code fences and heading structure validate;
- runtime baselines agree;
- pipeline order agrees across architecture, prompts, dashboard, and roadmap;
- signals remain observed and patterns inferred;
- opportunity mode is mutually exclusive;
- packet hash excludes volatile fields;
- contact origins and draft bindings are explicit;
- every AI stage has schema/prompt/error/test contracts;
- Docker local/server layouts are portable;
- the Codex prompt finds the knowledge base, implements one verified milestone, and updates durable state;
- `FILE_MANIFEST.md` is regenerated for every release.
