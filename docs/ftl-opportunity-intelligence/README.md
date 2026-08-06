# FTL Opportunity Intelligence Knowledge Base

**Specification version:** 2.1  
**Audit date:** 2026-08-05  
**Document status:** Normative implementation specification  
**System:** FTL Opportunity Intelligence & Outreach Platform  
**Audience:** Codex, FTL founders, and FTL engineers

## Purpose

This directory is the implementation knowledge base for a local-first, Dockerized platform that discovers public evidence of organizational demand, converts that evidence into explainable FTL opportunities, researches the organization, designs an appropriate **Create–Build–Deploy–Enable** engagement, identifies a legitimate contact route, and prepares human-approved outreach.

The system MUST remain a commercial-intelligence and opportunity-design environment for a premium creative technology studio. It MUST NOT degrade into a generic scraper, untraceable autonomous agent, or mass-email tool.

## Specification precedence

When documents conflict, Codex MUST follow this order:

1. Repository-root `AGENTS.md` or this directory's `AGENTS.md`.
2. `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`.
3. This `README.md`.
4. Numbered subsystem specifications `01`–`31` and prompt standard `33`.
5. `30_CODEX_IMPLEMENTATION_ROADMAP.md` for implementation order.
6. `00_FTL_OPPORTUNITY_INTELLIGENCE_PIPELINE_REFERENCE.md` as product context only.

The `00` document preserves the original concept. Any implementation example in it that conflicts with the audited specifications is superseded.

## Normative language

- **MUST**: required for correctness, integrity, security, or compatibility.
- **SHOULD**: preferred unless a documented Architecture Decision Record explains a deviation.
- **MAY**: optional and must not block the core product.

## Corrected end-to-end flow

```text
Search definitions and watched companies
    -> source discovery
    -> safe fetching and deterministic parsing
    -> normalized source records
    -> immutable snapshots and source artifacts
    -> observed signal events
    -> capability-gap classification
    -> company patterns, aggregation, and deterministic scoring
    -> selective public company research
    -> optional background deep research
    -> FTL solution design
    -> approved FTL asset matching
    -> buyer-role and public or explicit human-origin contact-route discovery
    -> deterministic opportunity packet
    -> outreach draft as exact-bound structured content units
    -> deterministic factual validation and human approval
    -> optional external email-draft creation
    -> interaction and reply tracking
    -> evaluation and policy feedback
```

### Important semantic boundaries

- A **source record** is a fetched public object.
- A **signal event** is an observed fact such as a new relevant posting.
- A **company pattern** is an inference over multiple observed signals.
- A **capability gap** is a bounded interpretation supported by evidence.
- A **solution hypothesis** is an editable commercial design, not a confirmed client requirement.
- A **contact route** has an explicit public or human origin; observation, freshness, deliverability, outreach eligibility, recommendation, and suppression remain separate.
- An **outreach draft** remains unsent until a human approves the exact version.

## Audited technical baseline

The first production implementation SHOULD use:

```text
Python 3.13
Django 5.2 LTS
PostgreSQL 18
psycopg 3
Celery 5.6
Redis-compatible broker (Redis or Valkey; Redis is acceptable for the first server)
django-celery-beat
OpenAI Python SDK + Responses API
Pydantic v2
HTTPX
selectolax or BeautifulSoup
extruct for JSON-LD
Playwright only as a fallback
Django templates + HTMX + Tailwind CSS
Docker Compose
```

Rationale and upgrade policy are recorded in `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`. Pin exact tested patch versions and image digests in the repository; do not depend on floating `latest` tags.

## Core architecture decisions

1. PostgreSQL is canonical. Redis and Celery messages are transport, never business state.
2. A transactional outbox closes the database-commit/broker-publish gap.
3. Celery task results are not stored as a second domain model; tasks normally ignore results and update durable `PipelineRun` and domain records.
4. Large raw HTML and report artifacts use Django's storage abstraction with database metadata and hashes. Local Docker volumes can later be replaced by S3-compatible storage without changing domain code.
5. The application owns workflow state. Use the OpenAI Responses API directly for bounded model calls. The OpenAI Agents SDK is optional for isolated experiments, not the orchestration backbone.
6. Public web research and private FTL matching are separate calls and trust boundaries.
7. Structured Outputs/Pydantic are mandatory for machine-consumed model results.
8. Research is two-pass: cited public research first, schema-constrained extraction second.
9. Model output is advisory. Python validates enums, evidence references, score ranges, and state transitions.
10. First-contact outreach is never auto-sent in the initial product.
11. Opportunity mode is one mutually exclusive enum plus confidence; company patterns remain distinct from observed signals.

## Local-first and server-ready constraints

1. The full application MUST run with Docker Compose on a laptop.
2. PostgreSQL and the broker MUST run as containers locally.
3. Persistent PostgreSQL, media/artifact, and backup data MUST use named volumes or bind mounts outside container layers.
4. `OPENAI_API_KEY` MUST be read at runtime. Local development may use `.env`; server deployment SHOULD use Compose secrets or another secret manager through `*_FILE` support.
5. Development and server deployment MUST use the same built image and migrations.
6. The base Compose file MUST keep PostgreSQL and the broker private. A development override MAY expose them on `127.0.0.1`.
7. Schema migration MUST run as one explicit release operation, never concurrently in every worker.
8. Long OpenAI research MUST use start/poll or webhook/retrieve tasks; a worker MUST NOT remain blocked for the full research duration.
9. Server migration MUST require only image deployment, environment/secrets, database restore, artifact transfer, and DNS/TLS configuration.

## Knowledge-base map

| Order | Document | Responsibility |
|---:|---|---|
| 00 | `00_FTL_OPPORTUNITY_INTELLIGENCE_PIPELINE_REFERENCE.md` | Original product reference; non-normative when superseded |
| 01 | `01_PRODUCT_SCOPE_AND_DOMAIN_LANGUAGE.md` | Product boundaries and canonical terms |
| 02 | `02_SYSTEM_ARCHITECTURE_AND_DATA_FLOW.md` | Components, trust boundaries, outbox, and stage contracts |
| 03 | `03_REPOSITORY_AND_DJANGO_APP_STRUCTURE.md` | Code organization and dependency rules |
| 04 | `04_DOCKER_LOCAL_DEVELOPMENT.md` | Local and server Compose architecture |
| 05 | `05_CONFIGURATION_AND_SECRETS.md` | Typed settings, secrets, and policy configuration |
| 06 | `06_DATABASE_SCHEMA_AND_MIGRATIONS.md` | PostgreSQL schema, constraints, artifacts, and outbox |
| 07 | `07_DOMAIN_STATES_AND_AUDIT_TRAIL.md` | State machines, ownership, history, concurrency |
| 08 | `08_SEARCH_DEFINITIONS_AND_DISCOVERY.md` | Search plans and daily discovery |
| 09 | `09_SOURCE_CONNECTORS_AND_FETCHING.md` | ATS, JSON-LD, generic web, safe fetch |
| 10 | `10_NORMALIZATION_SNAPSHOTS_DEDUPLICATION.md` | Canonical records and change detection |
| 11 | `11_SIGNAL_DETECTION_AGENT.md` | Deterministic signal service and optional evidence extractor |
| 12 | `12_CAPABILITY_GAP_CLASSIFIER.md` | FTL relevance, gaps, modes, and component judgments |
| 13 | `13_COMPANY_AGGREGATION_AND_SCORING.md` | Company patterns, features, and deterministic ranking |
| 14 | `14_COMPANY_RESEARCH_AGENT.md` | Two-pass bounded company research and categorized claims |
| 15 | `15_DEEP_RESEARCH_AGENT.md` | Selective background deep research |
| 16 | `16_CONTACT_DISCOVERY_AND_VERIFICATION.md` | Buyer roles plus public and explicit human-origin routes after solution design/asset matching |
| 17 | `17_FTL_KNOWLEDGE_AND_ASSET_LIBRARY.md` | Approved FTL offers, claims, and proof points |
| 18 | `18_SOLUTION_DESIGN_AGENT.md` | Create–Build–Deploy–Enable solution hypothesis |
| 19 | `19_OPPORTUNITY_PACKET_BUILDER.md` | Deterministic compact drafting context |
| 20 | `20_OUTREACH_DRAFTING_AGENT.md` | Structured drafting units with exact packet bindings and deterministic rendering |
| 21 | `21_FACTUAL_REVIEW_AND_APPROVAL.md` | Deterministic checks, optional AI critic, human gates |
| 22 | `22_INTERACTION_AND_REPLY_TRACKING.md` | Messages, replies, follow-up, and suppression |
| 23 | `23_DASHBOARD_UX_SPECIFICATION.md` | Page hierarchy and operational interface |
| 24 | `24_CELERY_ORCHESTRATION_AND_SCHEDULING.md` | Queues, outbox, retries, and scheduling |
| 25 | `25_OPENAI_CLIENT_MODEL_ROUTING_AND_COSTS.md` | Responses API abstraction and model policies |
| 26 | `26_OBSERVABILITY_AND_OPERATIONS.md` | Logs, metrics, health, cost, and recovery |
| 27 | `27_SECURITY_PRIVACY_AND_COMPLIANCE.md` | Prompt-injection, SSRF, access, data, and outreach safeguards |
| 28 | `28_TESTING_EVALUATION_AND_QUALITY_GATES.md` | Software tests and local AI evaluation harness |
| 29 | `29_BACKUP_RESTORE_AND_SERVER_MIGRATION.md` | Verified backups and local-to-server migration |
| 30 | `30_CODEX_IMPLEMENTATION_ROADMAP.md` | Ordered vertical implementation milestones |
| 31 | `31_TECHNICAL_REFERENCES.md` | Primary official references |
| 32 | `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md` | Audit findings and binding corrections |
| 33 | `33_AGENT_PROMPT_ENGINEERING_STANDARD.md` | Shared prompt, schema, safety, and evaluation standard |
| 34 | `34_CODEX_MASTER_EXECUTION_PROMPT.md` | Copy-ready Codex kickoff prompt |
| 35 | `35_CODEX_MILESTONE_PROMPT_TEMPLATE.md` | Bounded continuation prompt for one milestone |
| — | `AGENTS.md` | Repository-wide Codex rules |
| — | `IMPLEMENTATION_STATUS.md` | Living milestone/checklist template |
| — | `DECISIONS.md` | Architecture-decision log template |

## Recommended first operational release

The first operational release ends after milestone 7 in `30_CODEX_IMPLEMENTATION_ROADMAP.md`. It includes local login, source ingestion, normalized postings, snapshots, deduplication, observed signals, capability-gap classification, deterministic scoring, a review inbox, operations visibility, and verified backup/restore. It does not require deep research, contacts, or outreach.

## Global implementation conventions

- Use UTC in storage and `Europe/Berlin` only for display/scheduling.
- Use UUID primary keys; choose UUID4 by default unless an explicit ADR adopts application-generated UUID7.
- Treat URLs as unbounded text plus normalized URL hash; do not assume 255 characters.
- Use relational columns for queried/constrained fields and JSONB for raw or versioned provider/model payloads.
- Store large fetched bodies and generated reports through `SourceArtifact`/storage, not indefinitely as large database text fields.
- Every external record keeps provider, URL, retrieval time, parser version, and content hash.
- Every model run keeps model policy, prompt version, schema version, request/response IDs, usage, and source/input IDs.
- Never ask models for hidden chain-of-thought. Store concise evidence-backed rationales only.
- Make every service and task idempotent.
- Store observed facts, inferences, hypotheses, unknowns, and assumptions separately.
- Never use a model-generated person or email without provenance.
- Keep model IDs, reasoning effort, tools, thresholds, schedules, and budgets configurable and versioned.

## Codex starting point

Codex MUST read, in order:

1. `AGENTS.md`
2. this `README.md`
3. `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`
4. `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`
5. `30_CODEX_IMPLEMENTATION_ROADMAP.md`
6. the subsystem files for the current milestone

Then use `34_CODEX_MASTER_EXECUTION_PROMPT.md` and update `IMPLEMENTATION_STATUS.md` and `DECISIONS.md` as implementation progresses.
