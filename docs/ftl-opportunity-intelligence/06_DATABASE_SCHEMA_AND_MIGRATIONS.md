# 06 — PostgreSQL Database Schema and Migrations

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Data architecture  
**Audience:** Codex and FTL engineers

## 1. Purpose

Define canonical PostgreSQL entities, relationships, constraints, indexes, history, idempotency, and migration rules.

## 2. Principles

- PostgreSQL is the source of truth.
- Business state is normalized; raw external payloads remain available in JSONB.
- Append-only snapshots, audit events, and provider-call records preserve provenance.
- Unique constraints enforce idempotency.
- Soft archival/status transitions preserve history; destructive deletion is exceptional.
- Model output is never written directly without Pydantic and catalog-reference validation.
- Large binary files belong in approved file/object storage; PostgreSQL stores identity, metadata, and hashes.
- All timestamps use timezone-aware UTC.
- Models include `created_at`, `updated_at`, and where needed `row_version` for optimistic concurrency.

## 3. Django app ownership

| App | Primary entities |
|---|---|
| `accounts` | User, TeamRole |
| `companies` | Company, CompanyDomain, CompanyAlias, CompanyMergeReview |
| `sources` | SourceEndpoint, SourceCandidate, DiscoveryRun, FetchAttempt, SourceSnapshot |
| `jobs` | JobPosting, JobPostingSnapshot, PostingObservation, DuplicateRelationship, EvidenceCatalog, EvidenceItem |
| `signals` | SignalEvent, SignalAssessment, CapabilityGapRecord, CompanyPattern |
| `opportunities` | Opportunity, OpportunitySignal, CompanyAssessment, SolutionHypothesis, SolutionPhase |
| `research` | ResearchBrief, ResearchRun, ResearchSource, ResearchClaim, ClaimSourceSupport, ResearchConflict |
| `contacts` | BuyerRoleHypothesis, ContactPerson, ContactRoleHistory, ContactRoute, SuppressionEntry |
| `knowledge` | FTLClaim, OfferModule, Asset, KnowledgeRelease |
| `outreach` | OpportunityPacket, OutreachDraft, DraftContentUnit, DraftClaimBinding, EvidenceReview, ApprovalDecision |
| `interactions` | Interaction, ReplyClassification, FollowUpAction |
| `operations` | PipelineRun, PipelineStepRun, TaskOutbox, ProviderCall, WebhookEvent, AuditEvent, Lease |

## 4. Company identity

### 4.1 `Company`

```text
id UUID PK
legal_name text nullable
name text not null
normalized_name text not null
company_type enum nullable
industry_key text nullable
headquarters_country char(2) nullable
headquarters_city text nullable
employee_range enum nullable
description text nullable
strategic_fit_manual smallint nullable check 0..100
status enum active|archived|merge_review
created_at timestamptz
updated_at timestamptz
row_version bigint default 1
```

Do not enforce a globally unique company name.

### 4.2 `CompanyDomain`

```text
id UUID PK
company_id FK Company
hostname_ascii text not null
hostname_unicode text nullable
registrable_domain text not null
is_primary boolean default false
verification_status enum unverified|source_confirmed|human_verified|disputed
verification_source_url text nullable
verified_at timestamptz nullable
first_seen_at timestamptz
last_seen_at timestamptz
created_at timestamptz
updated_at timestamptz
```

Constraints:

- lowercase ASCII/IDNA normalized hostname;
- unique `(company_id, hostname_ascii)`;
- partial unique: one `is_primary=true` per company;
- a hostname mapped to multiple companies creates `CompanyMergeReview` unless explicitly allowed for a shared parent/hosting relationship;
- do not silently merge companies solely because they share a generic ATS host.

### 4.3 `CompanyMergeReview`

Stores candidate company IDs, evidence/source IDs, match methods, confidence, state, human decision, and audit reference.

## 5. Discovery and source records

### 5.1 `DiscoveryRun`

```text
id UUID PK
search_definition_id FK
logical_window_start/end timestamptz
run_reason enum scheduled|manual|backfill
status enum queued|running|partial|complete|failed|canceled
idempotency_key text unique
started_at/completed_at timestamptz
candidate_count/new_candidate_count integer
provider_call_id FK nullable
warnings JSONB
```

Unique logical-window constraints prevent duplicate scheduled runs.

### 5.2 `SourceCandidate`

```text
id UUID PK
discovery_run_id FK
url_original text
url_canonical text
url_sha256 char(64)
source_type_hint enum nullable
company_name_hint text nullable
company_domain_hint text nullable
title_hint text nullable
snippet_hint text nullable
matched_terms JSONB
candidate_confidence numeric(4,3)
status enum new|fetch_queued|registered|rejected|unsafe|duplicate
rejection_reason text nullable
created_at timestamptz
```

`snippet_hint` is not evidence and cannot be referenced by signal agents.

### 5.3 `SourceEndpoint`

```text
id UUID PK
company_id FK nullable
provider_type enum
base_url_original text
base_url_canonical text
tenant_key text nullable
configuration JSONB
status enum active|degraded|blocked|archived
robots_policy enum allowed|blocked|unknown|not_applicable
etag text nullable
last_modified text nullable
last_success_at/last_failure_at timestamptz nullable
consecutive_failures integer default 0
next_allowed_fetch_at timestamptz nullable
connector_key/version text
created_at/updated_at timestamptz
```

### 5.4 `FetchAttempt`

Every attempt exists even when no new snapshot is created.

```text
id UUID PK
source_endpoint_id FK
requested_url/final_url text
status enum fetched|not_modified|blocked|failed|too_large|unsupported
http_status integer nullable
started_at/completed_at timestamptz
elapsed_ms integer nullable
redirect_chain JSONB
response_headers_filtered JSONB
body_sha256 char(64) nullable
body_size_bytes bigint nullable
content_type text nullable
retryable boolean
error_code text nullable
safe_error_message text nullable
pipeline_run_id FK
```

### 5.5 `SourceSnapshot`

Immutable content snapshot.

```text
id UUID PK
source_endpoint_id FK
fetch_attempt_id FK
retrieved_at timestamptz
body_sha256 char(64)
content_type text
encoding text nullable
body_text text nullable
raw_payload JSONB nullable
storage_key text nullable
parser_hint text nullable
retention_class enum
created_at timestamptz
```

At least one of body/raw/storage reference is present. Use a check constraint.

## 6. Job postings and snapshots

### 6.1 `JobPosting`

```text
id UUID PK
company_id FK
source_endpoint_id FK
provider_external_id text nullable
canonical_url text
canonical_url_sha256 char(64)
current_snapshot_id FK nullable
title_current text
normalized_title text
status enum open|closed|expired|unknown
first_seen_at/last_seen_at timestamptz
closed_at timestamptz nullable
closure_reason enum nullable
successful_absence_count integer default 0
created_at/updated_at timestamptz
```

Partial uniqueness:

- `(source_endpoint_id, provider_external_id)` when external ID is present;
- canonical URL hash within the provider where appropriate.

### 6.2 `JobPostingSnapshot`

Immutable normalized domain snapshot.

```text
id UUID PK
job_posting_id FK
source_snapshot_id FK
normalizer_key/version text
content_sha256 char(64)
semantic_content_sha256 char(64)
title text
normalized_title text
department text nullable
employment_type enum nullable
seniority enum nullable
remote_type enum nullable
locations JSONB
description_text text
description_html_sanitized text nullable
language char(2) nullable
published_at/updated_at/valid_through timestamptz nullable
field_provenance JSONB
raw_normalized_payload JSONB
created_at timestamptz
```

Unique `(job_posting_id, content_sha256)` prevents duplicate snapshots.

### 6.3 `PostingObservation`

Records each successful poll and whether the posting was present, not modified, absent, or explicitly closed. Closure logic uses successful observations rather than wall-clock time alone.

### 6.4 `DuplicateRelationship`

```text
primary_posting_id
secondary_posting_id
relationship_type duplicate|translation|syndicated|related
method provider_id|canonical_url|content_hash|rule|semantic_review
confidence numeric
review_status automatic|needs_review|confirmed|rejected
source_priority first_party|secondary
```

Never delete the secondary posting to “deduplicate.”

## 7. Deterministic evidence

### 7.1 `EvidenceCatalog`

One catalog is built for a snapshot/version.

```text
id UUID PK
job_posting_snapshot_id FK
builder_version text
catalog_sha256 char(64)
created_at timestamptz
```

### 7.2 `EvidenceItem`

```text
id UUID PK
catalog_id FK
public_id text                  # EV-000001 within catalog
field_path text
exact_text text
normalized_text text
start_char integer nullable
end_char integer nullable
language char(2) nullable
content_sha256 char(64)
created_at timestamptz
```

Constraints:

- unique `(catalog_id, public_id)`;
- exact text must be present in the persisted normalized field when offsets are provided;
- no model creates evidence rows;
- evidence quoted in UI is loaded from this table.

## 8. Signals and assessments

### 8.1 `SignalEvent`

```text
id UUID PK
company_id FK
job_posting_id FK nullable
job_posting_snapshot_id FK nullable
signal_type enum
event_kind enum
occurred_at timestamptz nullable
observed_at timestamptz
capability_tags JSONB
confidence numeric(4,3)
idempotency_key text unique
status enum active|superseded|retracted|review_required
prompt_version text nullable
schema_version text
created_at timestamptz
```

Use a junction table `SignalEvidence(signal_event_id, evidence_item_id, support_type)` rather than copying quotes.

### 8.2 `SignalAssessment`

```text
id UUID PK
signal_event_id FK
ontology_version text
scoring_policy_version text
model_policy_snapshot JSONB
prompt_key/version text
schema_key/version text
structured_output JSONB
capability_relevance smallint nullable
commercial_actionability smallint nullable
long_term_system_potential smallint nullable
strategic_value smallint nullable
priority_score smallint nullable
opportunity_mode enum employment_only|external_service|hybrid|watch_signal|irrelevant|unknown nullable
mode_confidence numeric(4,3) nullable
mode_rationale text nullable
confidence numeric(4,3)
status enum completed|review_required|failed|superseded
input_sha256 char(64)
idempotency_key text unique
created_at timestamptz
```

`CapabilityGapRecord` stores one row per gap plus confidence/rationale; evidence is linked through a junction table.

## 9. Company aggregation and opportunities

### 9.1 `CompanyPattern`

Stores an inferred multi-signal pattern separately from observed events.

```text
id UUID PK
company_id FK
pattern_key enum
feature_cutoff_at timestamptz
rule_version text
input_signal_ids JSONB
input_sha256 char(64)
confidence numeric(4,3)
status active|superseded|review_required
narrative text nullable
prompt/model provenance JSONB nullable
created_at timestamptz
```

A `CompanyPattern` MUST reference at least two signals unless the configured rule explicitly supports a single-signal pattern. It never uses a `SignalEvent.signal_type` value.

### 9.2 `CompanyAssessment`

Stores deterministic features, score components, feature cutoff, policy version, optional narrative, selected signal IDs, selected company-pattern IDs, score coverage, and missing components.

### 9.3 `Opportunity`

```text
id UUID PK
company_id FK
title text
owner_id FK User nullable
primary_signal_id FK nullable
qualification_status enum
research_status enum
solution_status enum
outreach_status enum
relationship_stage enum
priority_score smallint nullable
entry_offer_key text nullable
long_term_operating_model enum nullable
infrastructure_option enum nullable
next_action_key text nullable
next_action_at timestamptz nullable
created_at/updated_at timestamptz
row_version bigint
```

Independent status columns are mandatory; do not collapse them into one generic status.

`OpportunitySignal` is a many-to-many table with relationship type and inclusion reason.

## 10. Research provenance

### 10.1 `ResearchRun`

```text
id UUID PK
opportunity_id FK
research_type enum standard|deep
status enum draft|queued|in_progress|source_complete|extracting|complete|partial|failed|expired|canceled
brief_id FK
provider_call_id FK nullable
external_response_id text nullable
report_markdown text nullable
report_sha256 char(64) nullable
source_registry_sha256 char(64) nullable
prompt/schema/model snapshots JSONB
started_at/completed_at timestamptz nullable
failure JSONB nullable
```

### 10.2 `ResearchSource`

```text
id UUID PK
research_run_id FK
public_id text                    # SRC-000001
canonical_url text
url_sha256 char(64)
title text nullable
publisher text nullable
source_type enum official_company|official_registry|official_report|press|job_page|other
retrieved_at timestamptz
published_at timestamptz nullable
content_hash text nullable
provider_source_metadata JSONB
created_at timestamptz
```

Unique `(research_run_id, public_id)` and `(research_run_id, url_sha256)` where appropriate.

### 10.3 `ResearchClaim`

```text
id UUID PK
research_run_id FK
public_id text                    # CLM-000001
claim_type observed_fact|inference|hypothesis|unknown
claim_category company_profile|signal_context|organizational_ownership|external_partner_context|infrastructure_privacy_governance|evidence_against|other
statement text
confidence numeric(4,3)
current_as_of date nullable
expires_at date nullable
status active|stale|disputed|superseded
conflict_group text nullable
created_at timestamptz
```

### 10.4 `ClaimSourceSupport`

Many-to-many support table:

```text
claim_id
research_source_id
support_type supports|contradicts|context_only
support_strength numeric(4,3) nullable
```

Observed facts require at least one `supports` relation, enforced in the service layer and tested.

## 11. Contacts and routes

### 11.1 `BuyerRoleHypothesis`

A role category, not a person.

### 11.2 `ContactPerson`

A durable publicly relevant person identity. It stores names/profile identity and first/last observation timestamps, but does not itself assert that a role or route is current.

### 11.3 `ContactObservation` / `ContactRoleHistory`

Tracks source-backed person-role-company observations over time.

```text
id UUID PK
contact_person_id FK
company_id FK
role_label text
department text nullable
seniority enum nullable
source_id FK ResearchSource
first_observed_at/last_observed_at timestamptz
observation_status enum published_officially|published_third_party|human_confirmed|unconfirmed|disputed
role_status enum current|historical|unknown
created_at timestamptz
```

### 11.4 `ContactRoute`

```text
id UUID PK
company_id FK
contact_person_id FK nullable
buyer_role_hypothesis_id FK nullable
route_type enum role_email|individual_business_email|contact_form|professional_profile|phone|warm_introduction|existing_relationship|event_connection|other
route_origin enum public_source|human_entered|existing_relationship|event
value_encrypted text nullable
value_display_redacted text nullable
normalized_value_hmac char(64) nullable
primary_source_id FK ResearchSource nullable
created_by_user_id FK User nullable
provenance_note text nullable
retrieved_at/last_checked_at timestamptz nullable
observation_status enum published_officially|published_third_party|human_confirmed|unconfirmed|disputed
freshness_status enum current|stale|unknown
deliverability_status enum unknown|delivered|replied|bounced|invalid
outreach_eligibility enum unreviewed|eligible_after_human_review|blocked|suppressed
status active|stale|suppressed|invalid
row_version bigint default 1
created_at/updated_at timestamptz
```

`ContactRouteEvidence(route_id, research_source_id, evidence_item_id nullable, support_type)` stores every public source/evidence relation. `primary_source_id` is a convenience pointer, not the only provenance record.

Required database/service constraints:

- `route_origin=public_source` requires at least one `ContactRouteEvidence` row and a non-null `primary_source_id` before the route can become active;
- `route_origin` in `human_entered|existing_relationship|event` requires `created_by_user_id` and a non-empty `provenance_note`; a public source is optional;
- the automated public-route extractor may create only `route_origin=public_source` and may not create `warm_introduction`, `existing_relationship`, or `event_connection` routes;
- values are encrypted with an application-managed envelope-encryption key loaded from the secret provider; normalized keyed hashes use a separate HMAC key for deduplication and suppression;
- publication proves route existence only. It does not prove deliverability, permission, or outreach eligibility;
- a guessed email pattern MUST NOT create a route in the initial product.

### 11.5 `SuppressionEntry`

Unique hashes for organization/person/route plus reason, scope, source interaction, created by, and immutable timestamp. Suppression checks are synchronous and cannot be bypassed by model output.

## 12. FTL knowledge and solutions

FTL claims/offers/assets are versioned. Confidentiality and external-use approval are explicit.

`SolutionHypothesis` stores the complete strict output, canonical JSON, `content_sha256`, input version vector, row version, status, human editor, and approval. `SolutionPhase` may be normalized for UI ordering and reporting. `KnowledgeRelease`, `Asset`, `FTLClaim`, `OfferModule`, and communication-policy releases likewise expose immutable version/content hashes for deterministic packet manifests.

## 13. Opportunity packets, drafts, and reviews

### 13.1 `OpportunityPacket`

Immutable generated packet with schema version, canonical JSON, input version vector, SHA-256, status, stale reasons, and created by.

### 13.2 `OutreachDraft`

Stores the immutable model result, exact packet/hash, prompt/schema/model provenance, selected route, language/channel, deterministic rendered subject/body/short-message strings, rendering-policy version, status, and `never_sent=true` default. Regeneration or editing creates a new version.

### 13.3 `DraftContentUnit`

Normalizes each model-authored unit so the rendered message can be audited without fuzzy substring matching.

```text
id UUID PK
outreach_draft_id FK
unit_ref text                    # SUB-1, BODY-1, SHORT-1
unit_type enum subject|body_block|short_message_block
kind enum company_observation|company_inference|ftl_positioning|offer_hypothesis|proof_point|cta|other
sort_order integer
text text
text_sha256 char(64)
assumption_disclosed boolean default false
created_at timestamptz
```

Unique `(outreach_draft_id, unit_ref)` and `(outreach_draft_id, unit_type, sort_order)` where order applies.

### 13.4 `DraftClaimBinding`

```text
id UUID PK
draft_content_unit_id FK
reference_type enum signal_evidence|research_claim|solution_field|ftl_claim|asset|human_instruction
reference_public_id text
support_role enum supports|context_only
created_at timestamptz
```

The service validates every reference against the exact `OpportunityPacket`. Company observations/inferences, FTL positioning, offer hypotheses, and proof points have stage-specific minimum bindings. CTA units may be unbound. Python renders final plaintext from ordered units; model-provided free-form body text is not canonical.

### 13.5 `EvidenceReview`

Automated review output. It cannot set human approval.

### 13.6 `ApprovalDecision`

Human user, decision, draft version/rendered-content hash, packet stable-input hash, route row version, timestamp, comments, and optional expiration. Editing any unit, subject, route, packet input, or rendered provider content invalidates the approval.

## 14. Operations and durable outbox

### 14.1 `TaskOutbox`

```text
id UUID PK
topic text
payload JSONB
idempotency_key text unique
status pending|publishing|published|failed|canceled
available_at timestamptz
attempts integer
last_error_code text nullable
last_error_message text nullable
claimed_by text nullable
claimed_at timestamptz nullable
published_at timestamptz nullable
created_at timestamptz
```

Dispatcher uses `SELECT ... FOR UPDATE SKIP LOCKED` or equivalent safe claim logic.

### 14.2 `PipelineRun` and `PipelineStepRun`

Store logical run, object, stage, status, heartbeat, attempts, input/output IDs, error, correlation, and timing.

### 14.3 `ProviderCall`

Store request hash, provider, operation, model policy snapshot, response ID, status, usage, tool calls, cost metadata, safe error, and retention classification.

### 14.4 `WebhookEvent`

Unique provider + webhook ID, signature status, event type, referenced response ID, received/processed times, safe payload subset, and processing error.

### 14.5 `AuditEvent`

Append-only actor, action, object, before/after summaries, request/trace ID, reason, and timestamp.

## 15. Indexes

At minimum:

- B-tree indexes on all foreign keys and frequently filtered statuses/dates;
- partial indexes for active/open/current rows;
- unique idempotency keys;
- GIN indexes for selected JSONB fields only after measured query need;
- PostgreSQL full-text indexes on posting descriptions and company names;
- `pg_trgm` indexes for title/company fuzzy search;
- source URL hashes rather than oversized raw-URL unique indexes;
- `(company_id, observed_at desc)` on signals;
- `(opportunity_id, created_at desc)` on research/drafts/interactions;
- `(status, available_at)` on `TaskOutbox`;
- `(status, heartbeat_at)` on pipeline runs.

Do not add embedding/vector storage until an evaluated use case justifies it. Semantic deduplication can begin with provider/model computation stored as review metadata, not a mandatory vector database.

## 16. Constraints and invariants

Implement database constraints where possible:

- score/check ranges;
- confidence ranges;
- one primary domain per company;
- immutable snapshot rows through service/model policy;
- unique logical schedule windows;
- unique prompt/policy versions;
- one active approval for an exact draft hash;
- contact observation, freshness, deliverability, and outreach eligibility remain independent;
- no contact route exists without a registered public source or explicit human-origin record;
- one canonical posting per provider external ID;
- one outbox idempotency key.

Cross-row business invariants remain in transactional domain services with tests.

## 17. Migration policy

1. Migrations are committed and reviewed.
2. `makemigrations --check --dry-run` passes in CI.
3. Data migrations are explicit, reversible when feasible, and batch large updates.
4. Destructive changes use expand-migrate-contract across releases.
5. Never edit a migration already applied in shared environments.
6. Add indexes concurrently for large production tables where supported and necessary.
7. Test migration from the previous released schema and a fresh install.
8. Backup before production migrations with material risk.
9. Migration services fail deployment on error.
10. PostgreSQL major upgrades use supported dump/restore or upgrade procedures, not blind volume copying.

## 18. Seed/bootstrap command

Provide an idempotent management command:

```text
python manage.py bootstrap_ftl_platform
```

It creates or updates:

- roles/permissions;
- enums/ontology releases where represented as data;
- scoring policies;
- prompt activation metadata;
- FTL offer modules and public assets from Git;
- default schedules;
- model-policy placeholders with disabled provider state.

It never creates a production admin password or embeds secrets.

## 19. Acceptance criteria

- Fresh migrations create the complete schema.
- Migration from the previous revision is tested.
- Duplicate scheduled/task/agent calls cannot duplicate canonical records.
- Evidence/source catalog references are enforced.
- Company multi-domain and merge-review behavior is tested.
- Task publication survives broker outage through outbox retry.
- Full-text dashboard queries use intended indexes.
- No contact form creates a fake person.
- No inferred email is stored as an observed route.
- Company patterns remain distinct from observed signal events.
- Opportunity mode is one enum plus confidence, not overlapping probabilities.
- Editing a draft invalidates prior approval.
- Restore into a clean PostgreSQL container reproduces counts and key constraints.
