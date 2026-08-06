# 02 — System Architecture and Data Flow

**Specification version:** 2.1  
**Primary owner:** Platform architecture

## Purpose

Define the deployable components, trust boundaries, reliable asynchronous execution, and exact stage contracts for a modular monolith that runs locally and later on one or more servers without redesign.

## Architectural objective

```text
Browser
  -> reverse proxy
  -> Django web application
       -> PostgreSQL (canonical domain state)
       -> Django storage (large source/report artifacts)
       -> transactional outbox
       -> OpenAI/public web through integration adapters

Outbox dispatcher
  -> Celery broker

Celery workers
  -> discovery/fetch/parse
  -> classification/aggregation
  -> research/deep-research polling
  -> solution/contact/drafting/review
  -> maintenance/backup coordination

Celery Beat
  -> schedules durable commands/outbox records
```

The first deployment is a modular monolith. Do not introduce microservices, Kafka, Kubernetes, or a separate JavaScript SPA before measured operational need.

## Components

| Component | Responsibility | Canonical state? |
|---|---|---:|
| Django web | Auth, permissions, forms, pages, API/webhook endpoints | No; writes PostgreSQL |
| PostgreSQL | Domain records, policies, audit, runs, outbox | **Yes** |
| Django storage | Compressed raw HTML, reports, exports, attachments | Metadata in PostgreSQL |
| Celery broker | Short task messages | No |
| Celery workers | Execute idempotent commands | No |
| Celery Beat | Schedule commands | No |
| Outbox dispatcher | Publish committed commands reliably | State in PostgreSQL |
| OpenAI adapter | Responses API, parsing, usage, citations, webhooks | No |
| Source adapters | ATS feeds, JSON-LD, HTML, Playwright | No |

## Corrected pipeline

```text
Discovery
  -> Fetch and parse
  -> Normalize and snapshot
  -> Observed SignalEvent
  -> SignalAssessment / CapabilityGap
  -> CompanyPattern + CompanyAssessment
  -> CompanyResearchReport
  -> optional DeepResearchReport
  -> SolutionHypothesis
  -> FTLAssetMatch
  -> BuyerRoleHypothesis + ContactObservation/ContactRoute
  -> OpportunityPacket
  -> OutreachDraft + ClaimBinding
  -> ReviewFinding + HumanApproval
  -> Interaction / ReplyAssessment / FollowUp
```

Asset matching follows solution design because proof points must support the proposed engagement rather than drive it. Buyer-role and contact-route discovery then use the approved/current solution requirements and the explicit asset-selection result (including a valid zero-asset result). Research may preserve organizational-ownership context, but it does not create final buyer-role hypotheses or named contacts.

## Trust boundaries

### Untrusted

- browser input;
- URLs, redirects, headers, and fetched documents;
- job descriptions and email bodies;
- model output;
- webhook bodies before signature verification;
- third-party profile and contact data.

### Approved internal

- active FTL knowledge release;
- approved claims and public assets;
- human-approved solution and draft versions;
- access and suppression policy.

### Separation rule

Public research calls receive only public company/signal context. They do not receive private FTL data. A later no-web call combines the validated public research with approved FTL knowledge.

## Reliable command dispatch

`transaction.on_commit()` alone does not close the failure window where a database commit succeeds but broker publication fails. Use a transactional outbox.

```text
HTTP/task service transaction:
  1. write domain records
  2. write TaskOutbox row with unique idempotency key
  3. commit

Dispatcher:
  4. claim unpublished outbox rows with SELECT ... FOR UPDATE SKIP LOCKED
  5. publish short Celery message containing command/outbox ID
  6. mark published_at and broker_message_id
  7. retry stale unpublished rows
```

Tasks reload canonical records by ID. Task messages MUST NOT contain source bodies, secrets, full research reports, or mutable business state.

## Stage contracts

### DiscoveryCommandV1

```json
{
  "schema_version": "1.0",
  "search_definition_id": "uuid",
  "run_reason": "scheduled|manual|backfill",
  "window_start": "ISO-8601",
  "window_end": "ISO-8601",
  "requested_by_user_id": null,
  "idempotency_key": "discovery:<definition>:<window>"
}
```

### SourceCandidateV1

```json
{
  "candidate_id": "uuid",
  "url": "https://...",
  "normalized_url": "https://...",
  "url_hash": "sha256",
  "source_type_hint": "personio|greenhouse|lever|ashby|jsonld|html|unknown",
  "company_hint": "...",
  "provider_external_id": null,
  "discovery_evidence": "...",
  "discovered_at": "ISO-8601"
}
```

### IngestionOutcomeV1

```json
{
  "job_posting_id": "uuid",
  "snapshot_id": "uuid",
  "source_artifact_id": "uuid|null",
  "change_type": "new|unchanged|cosmetic|material|closed|reopened",
  "changed_fields": [],
  "observed_event_required": true,
  "duplicate_relationship_id": null
}
```

### Subsequent contracts

Use the versioned schemas defined in files `11`–`22`. Every schema has:

- `schema_version`;
- stable record IDs;
- source/input version IDs;
- enums rather than free-form state strings;
- bounded confidence/score values;
- warnings/unknowns where relevant.

## Synchronous versus asynchronous work

### Synchronous

- read/filter pages;
- small validated form submissions;
- state-transition request and outbox creation;
- human approval/rejection;
- health endpoints;
- webhook signature verification and event persistence.

### Asynchronous

- discovery and source polling;
- network fetching and Playwright;
- model calls;
- research and extraction;
- contact-route research;
- drafting and optional AI critic;
- exports, backups, cleanup, stale-run recovery.

## Long-running OpenAI work

Deep research uses short tasks:

```text
start request -> persist external_response_id -> return
webhook or scheduled poll -> retrieve canonical response -> persist artifact
structured extraction task -> validate/persist claims -> mark complete
```

A Celery worker MUST NOT sleep or poll in a loop for minutes. Local development uses polling. A server uses verified webhook notification plus polling as recovery.

## Idempotency keys

```text
discovery:{definition_id}:{window_start}:{window_end}
fetch:{source_item_key}:{retrieval_policy_version}
ingest:{source_item_key}:{body_hash}:{parser_version}
signal:{snapshot_id}:{event_type}:{signal_policy_version}
classify:{signal_event_id}:{prompt_version}:{model_policy_version}
aggregate:{company_id}:{window_end}:{aggregation_policy_version}
research:{opportunity_id}:{brief_hash}:{research_policy_version}
solution:{opportunity_id}:{research_set_hash}:{knowledge_release_id}:{prompt_version}
asset_match:{solution_id}:{knowledge_release_id}:{asset_policy_version}
contacts:{opportunity_id}:{solution_id}:{asset_match_id}:{contact_policy_version}
packet:{stable_input_hash}
draft:{packet_hash}:{channel}:{language}:{prompt_version}
review:{draft_id}:{draft_version}:{review_policy_version}
```

Database unique constraints, not only application checks, enforce uniqueness.

## Failure contract

```json
{
  "status": "failed",
  "stage": "classification",
  "error_code": "SCHEMA_VALIDATION_FAILED",
  "retryable": true,
  "attempt": 2,
  "max_attempts": 4,
  "provider_request_id": null,
  "context": {"signal_event_id": "uuid"},
  "safe_error_summary": "Model response did not validate against schema."
}
```

Do not store secrets or entire untrusted bodies in failure metadata.

## Artifact storage

Use a `SourceArtifact` record with storage key, content type, compression, size, SHA-256, source URL, created time, retention class, and optional expiry. The local backend is a named Docker volume. A future server may use S3-compatible object storage through Django `STORAGES` with no domain-model change.

## Acceptance criteria

- Every boundary has a versioned Pydantic schema.
- Database-to-broker publication is recoverable through the outbox.
- Tasks invoke services and reload state by ID.
- Repeating a command cannot duplicate domain records.
- Public and private AI contexts are demonstrably separated.
- Deep-research completion survives worker/web restarts.
- Large artifacts can move from local filesystem to object storage without schema redesign.
