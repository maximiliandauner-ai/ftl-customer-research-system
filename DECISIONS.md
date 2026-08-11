# Architecture Decision Log

**Purpose:** Record implementation decisions and justified deviations that arise while Codex or FTL engineers build the software. The audited decisions in `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md` are already binding and do not need to be duplicated here.

## Rules

- Add a decision before implementing a non-trivial deviation from the knowledge base.
- Never edit an accepted decision to hide history. Add a superseding decision.
- Link the relevant issue, plan, migration, pull request, or commit when available.
- A decision may not weaken security, evidence provenance, suppression, or human-approval rules without founder and legal/security review.

## Status values

```text
proposed
accepted
rejected
superseded
deprecated
```

### ADR-013 — Protect literal contact observations with separate encryption and lookup keys

**Date:** 2026-08-06  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `16_CONTACT_DISCOVERY_AND_VERIFICATION.md`, `18_SOLUTION_DESIGN_AGENT.md`, `27_SECURITY_PRIVACY_AND_COMPLIANCE.md`, `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`  
**Related implementation:** `apps/contacts/`, `config/runtime.py`, `scripts/bootstrap_env.py`

#### Context

Buyer roles are hypotheses about responsibilities, while a contact route is a separately observed and potentially sensitive fact. Public-source parsing must not turn role inference into guessed people or addresses, must retain exact provenance without exposing sensitive source fragments, and must support synchronous suppression without decrypting every stored route.

#### Decision

Derive buyer-role categories deterministically from the exact approved solution requirements and their supplied evidence identifiers. Scan only already-registered `official_company` research sources whose registrable domain matches the company, using the shared SSRF-safe fetcher. Extract only literal `mailto:`, `tel:`, form-action, and contact-link observations after removing inactive or executable markup; zero routes is a valid result. Encrypt raw contact-source bodies, sensitive exact evidence text, and email/phone/human route values with AES-256-GCM. Use a separate keyed HMAC for equality, deduplication, and suppression and persist a key identifier for rotation. Public extraction always records public origin, unknown deliverability, and unreviewed eligibility. Human-origin routes require an actor and provenance, while eligibility, legal review, recommendation, suppression, and exact opportunity selection remain explicit human operations.

#### Alternatives considered

- Infer a likely address from a person or domain, rejected because no address may be guessed.
- Store source markup or addresses in plaintext PostgreSQL fields, rejected because ordinary database reads, logs, and views must not expose protected contact data.
- Use deterministic encryption for lookup, rejected because a separate HMAC gives stable lookup without weakening authenticated randomized encryption.
- Let public parsing create warm-introduction or existing-relationship routes, rejected because only a human can establish those origins and their provenance.

#### Consequences

Fresh environments receive two independent generated local keys; enabling contact research without both valid 32-byte keys fails configuration checks. Key rotation needs an explicit future re-encryption procedure. Contact scans can complete successfully with role hypotheses and no route. A reviewed route can be selected for a future packet, but this milestone creates no draft, email, or send record.

#### Validation

Verify exact solution/evidence binding, company-domain source selection, safe fetch and redirect policy, hostile-markup removal, guessed-address rejection, encrypted artifacts/evidence/routes, HMAC deduplication and suppression, actor/provenance requirements, independent review states, exact selection, replay safety, PostgreSQL immutability triggers, permissions, and authenticated real-HTTP rendering.

#### Supersedes / superseded by

None.

### ADR-012 — Separate immutable knowledge releases from activation and prefilter assets

**Date:** 2026-08-06  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `17_FTL_KNOWLEDGE_AND_ASSET_LIBRARY.md`, `18_SOLUTION_DESIGN_AGENT.md`, `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`  
**Related implementation:** `apps/knowledge/`, `apps/solutions/`, `knowledge_base/`

#### Context

Editorial files must be deployable and reviewable without silently changing the offers, claims, or assets available to production logic. Asset selection must never expose confidential, embargoed, stale, unapproved, or unhealthy-link collateral to a model or downstream outreach path, and an empty reviewed library must not induce fabricated proof.

#### Decision

Append each strictly validated editorial catalog as an immutable `KnowledgeRelease` bound to its source commit and manifest hash. Keep the active release in a separate mutable registry pointer and append an actor/reason activation event for every change. Solution versions bind the exact active release and current research hashes. Python filters all asset eligibility dimensions before deterministic matching, caps selections at two, and treats zero selected assets as valid. Activation invalidates dependent current solution state without mutating historical releases, versions, or matches.

#### Alternatives considered

- Read editorial JSON directly on each request, rejected because deploy-time file changes would bypass durable review, audit, and reproducibility.
- Activate automatically after a successful sync, rejected because validation and human release authority are separate concerns.
- Ask a model to filter the full asset library, rejected because confidential or ineligible assets must be excluded before any model boundary.
- Require at least one asset, rejected because this would encourage invented or unsafe collateral when the reviewed catalog has no suitable entry.

#### Consequences

Editors perform an explicit sync, review, and activation sequence. Historical solutions remain reproducible and can be marked stale when inputs change. The initial release is operational with an empty asset catalog, but real collateral requires reviewed metadata before it can appear in a match.

#### Validation

Verify catalog cross-references and URL policy, sync idempotency, activation audit/history, PostgreSQL immutability triggers, confidential/stale/unapproved exclusion, zero-to-two selection, research/knowledge invalidation, exact approval binding, replay safety, role permissions, and real-HTTP rendering.

#### Supersedes / superseded by

None.

## Template

### ADR-XXX — Title

**Date:** YYYY-MM-DD  
**Status:** proposed  
**Owners:**  
**Related specifications:**  
**Related implementation:**

#### Context

Describe the problem, constraints, and why a decision is required.

#### Decision

State the selected option precisely.

#### Alternatives considered

- Option A
- Option B

#### Consequences

Describe benefits, costs, migration implications, security effects, operational effects, and follow-up work.

#### Validation

List tests, benchmarks, migration rehearsal, or review required to confirm the decision.

#### Supersedes / superseded by

None.

### ADR-011 — Register public research sources before isolated extraction

**Date:** 2026-08-06  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `14_COMPANY_RESEARCH_AGENT.md`, `25_OPENAI_CLIENT_MODEL_ROUTING_AND_COSTS.md`, `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`  
**Related implementation:** `apps/providers/openai.py`, `apps/research/services.py`, `apps/research/models.py`

#### Context

A single model call that both browses and emits machine-consumed facts could invent or alter citations, mix private FTL context into public research, and make it impossible to distinguish a durable provider report from a validated local claim registry.

#### Decision

Run standard research as two durable provider operations. The first uses the Responses web-search tool with only public company/job context and stores a cited plain-text report plus the provider source list. Python canonicalizes those exact URLs and assigns immutable local `SRC-` IDs. The second call has no tools and receives only the persisted report, registered sources, and selected signal/evidence IDs through a strict Structured Output contract. Python rejects fabricated/ambiguous references, assigns local `CLM-` IDs, renders the dossier deterministically, and preserves a partial report if extraction fails. Model, tool, reasoning, retention, and budgets remain in immutable active policies; live calls are feature-gated.

#### Alternatives considered

- One web-enabled structured call, rejected because source registration and extraction would share one untrusted boundary.
- Let extraction emit URLs directly, rejected because machine output must reference only the provider-derived registry.
- Store report Markdown as trusted rendered HTML, rejected because fetched/provider text is untrusted and the UI must escape it.

#### Consequences

Research has an extra step and durable artifact, but citations, source URLs, claims, failures, and replay are independently observable. Private FTL knowledge cannot enter the public pass. PostgreSQL holds business state and immutable metadata; Django storage holds the bounded report body.

#### Validation

Verify current SDK call signatures, no-tool extraction, private-context absence, source canonicalization, fabricated reference rejection, report integrity, partial failure preservation, duplicate delivery, database immutability, role boundaries, and real-HTTP escaped rendering.

#### Supersedes / superseded by

None.

### ADR-010 — Preserve inference and ranking history with coverage-aware Python scoring

**Date:** 2026-08-06  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `12_CAPABILITY_GAP_CLASSIFIER.md`, `13_COMPANY_AGGREGATION_AND_SCORING.md`  
**Related implementation:** `apps/signals/classification.py`, `apps/opportunities/services.py`

#### Context

Job evidence can support capability overlap while vendor receptivity, contactability, portfolio proof, strategic fit, and continued-partnership potential remain unknown. Treating those unknowns as zero would create false negative precision, while letting a model calculate final scores or routing would violate the audited ownership boundary.

#### Decision

Persist one strict, evidence-bound assessment output with exactly one opportunity mode. Python computes signal and company scores from versioned weights by normalizing over known components and applying a modest explicit coverage penalty. Every company feature stores cutoff, input IDs/hash, unit, and builder version. Policy reruns append assessments and supersede prior derived records only after success. Human mode and qualification decisions are separate actor/reason records and remain authoritative across automatic rescoring.

#### Alternatives considered

- Treat unknown dimensions as zero, rejected because missing evidence is not negative evidence.
- Let model output set the final score or qualification, rejected because ranking/state ownership is deterministic Python and human policy.

#### Consequences

Scores are reproducible and decomposable, low coverage is visible, and unknowns are never silent negatives. Concurrent aggregation may append multiple valid cutoff snapshots, but one database constraint protects the current active company/use-case opportunity. Observed signals remain distinct from inferred patterns.

#### Validation

Validate exact formula/coverage, strict enum and evidence references, replay, policy history, PostgreSQL immutability and active-opportunity uniqueness, retraction, human overrides, and current multi-signal live data through the ranked UI.

#### Supersedes / superseded by

None.

### ADR-009 — Make deterministic observed signals the default and supersede by policy version

**Date:** 2026-08-06  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `11_SIGNAL_DETECTION_AGENT.md`, `27_SECURITY_PRIVACY_AND_COMPLIANCE.md`, `28_TESTING_EVALUATION_AND_QUALITY_GATES.md`, `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`  
**Related implementation:** `apps/jobs/models.py`, `apps/signals/`, `prompts/signal_detector/v2.0.0.md`

#### Context

Observed signal detection must work with provider access disabled, preserve exact source quotes, reject instruction-like source content, and stay replay-safe. Keyword selection can also evolve: a broad substring matcher produced an `etl` false positive inside “quietly” during live browser QA. Rewriting or deleting historical signals would hide why a policy changed, while leaving multiple policy results active would make the inbox ambiguous.

#### Decision

Use a fully deterministic, versioned default detector over immutable normalized snapshot catalogs. Catalog items own stable `EV-` IDs, exact text/offsets/hashes, and are never created by a model. Capability rules use token/phrase boundaries and a versioned ontology; generic AI and instruction-like segments produce no capability signal. The strict canonical agent contract and prompt are retained for a future policy-gated no-web adapter, but no provider call is required or enabled in this milestone.

Every eligible lifecycle event schedules a new run for a new detector/ontology version. Only after the newer attempt completes successfully, Python retracts prior active results for that same change event as `superseded`, records the replacement IDs (which may be empty), and appends system audits. Historical attempts, signals, evidence links, and outputs remain queryable. Human false-positive retraction remains separate, permissioned, reasoned, and audited.

#### Alternatives considered

- Require a model for all signal detection, rejected because the product must work offline, simple lifecycle/capability evidence is deterministic, and provider failure must not block ingestion.
- Update prior signal rows in place, rejected because it destroys policy history and makes replay/evaluation unverifiable.
- Leave all historical detector results active, rejected because operators would see duplicates and obsolete false positives without a canonical current result.
- Match raw substrings, rejected after live evidence demonstrated token collisions inside unrelated words.

#### Consequences

Signal behavior is operational without credentials and easy to test. Policy upgrades add run/output history and may increase storage, but no evidence is lost. A later optional model detector must use the same central provider adapter, canonical contract, catalog validation, and supersession rule; it cannot set scores, opportunity state, approval, or outreach state.

#### Validation

Test exact offsets/hashes, English/German terms, generic-AI/injection/token-collision no-signal outcomes, invalid IDs/tags/event kinds/commercial rationale, replay, newer-policy supersession, PostgreSQL immutability triggers, role/CSRF boundaries, and real-HTTP provenance. Reprocess a real public feed and visually inspect an active exact quote containing the matched phrase.

#### Supersedes / superseded by

None.

### ADR-008 — Gate provider calls through immutable database policy and conservative reservations

**Date:** 2026-08-06  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `08_SEARCH_DEFINITIONS_AND_DISCOVERY.md`, `24_CELERY_ORCHESTRATION_AND_SCHEDULING.md`, `25_OPENAI_CLIENT_MODEL_ROUTING_AND_COSTS.md`, `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`  
**Related implementation:** `apps/providers/`, `apps/discovery/`, `apps/operations/management/commands/bootstrap_ftl_platform.py`

#### Context

Discovery must remain useful without a model, but optional public web search needs current tool syntax, strict output, queryable provenance, and enforceable cost/concurrency controls. Configuration flags alone cannot preserve the exact reviewed model/tool/reasoning/retention policy used by a historical call. Provider pricing is not yet encoded sufficiently to calculate exact cost from token usage.

#### Decision

All OpenAI access goes through one typed Responses adapter. An immutable active `ModelPolicy` points to a dated `ModelCapability`; the database policy owns model, tool, reasoning, output, retention, per-run, stage-period, and concurrency bounds. Runtime settings add account-period and concurrency ceilings. Before egress, the adapter locks the policy/capability, records a queued `ProviderCall`, validates capability and `store=false`, and conservatively reserves the request's maximum cost against daily/monthly totals. It then marks the call running and invokes current `web_search` plus strict Pydantic Structured Outputs. Refusal, incomplete, schema/catalog-reference, policy, budget, rate, and API outcomes remain durable. Search snippets remain diagnostic candidate metadata and cannot enter evidence.

Known endpoints never require this adapter: a discovery run creates ordinary source-ingestion outboxes for them. Discovery execution itself uses an expiring PostgreSQL lease so duplicate worker deliveries retry without overlapping effects.

#### Alternatives considered

- Put model IDs and tool arguments in discovery services, rejected because provider syntax and capability changes would leak across business code and historical policy would be ambiguous.
- Treat configured budgets as display-only values, rejected because optional calls must fail closed before egress.
- Estimate an exact monetary charge with an unreviewed pricing table, rejected because a false exact cost is less safe than conservative maximum-cost reservation.
- Let Celery task state or Redis locks own discovery concurrency, rejected because canonical coordination must survive broker loss.

#### Consequences

Enabling web discovery requires explicit flags, a credential, and an active compatible database policy. Conservative reservations may block earlier than actual billing until reviewed pricing/actual-cost rollups are added, but cannot overspend the declared ceiling. Capability upgrades create a new policy/version rather than silently changing old runs. The standard adapter is reusable by later research stages, which must add their own typed operation without bypassing it.

#### Validation

Mock current SDK `responses.parse`, source-list inclusion, strict schema, response-ID persistence, `store=false`, budget blocking before API invocation, invalid source references, logical-window idempotency, lease exclusion, PostgreSQL active-version constraints, disabled-provider operation, and a real watched-endpoint run through outbox/Celery.

#### Supersedes / superseded by

None.

### ADR-006 — Normalize provider feeds deterministically before interpretation

**Date:** 2026-08-06  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `09_SOURCE_CONNECTORS_AND_FETCHING.md`, `10_NORMALIZATION_SNAPSHOTS_DEDUPLICATION.md`, `27_SECURITY_PRIVACY_AND_COMPLIANCE.md`  
**Related implementation:** `apps/jobs/connectors/`, `apps/jobs/services.py`, `apps/jobs/models.py`

#### Context

Provider job feeds differ materially in identity, content, location, and markup structure. Allowing a generic parser to mask a known-provider schema change would silently corrupt canonical state, while storing only current rows would destroy the evidence needed for later change classification and scoring.

#### Decision

Select exactly one versioned deterministic connector using an explicit endpoint provider, documented provider hostname/content signature, JSON-LD JobPosting presence, then conservative generic HTML as the final fallback. Known-provider failure never falls through. Verify immutable artifact size and SHA-256 before parsing; reject XML DTD/entities/external references and bound JSON/structured output. Store searchable normalized fields and current state in PostgreSQL, retain every normalized snapshot and observation append-only, and keep the raw source body in Django storage only. Provider IDs are unique within the mapped endpoint/provider; cross-source identity remains an explicit later deduplication decision.

#### Consequences

Normalization is reproducible and testable without a model or network. Connector/version changes create explicit reparse runs and never rewrite history. Source schema changes degrade the endpoint visibly but cannot close existing postings. Full/semantic hashes are available to milestone 4, while no premature cross-source auto-merge is introduced.

#### Validation

Fixture every connector family and hostile input; verify task replay, unchanged content, artifact integrity, PostgreSQL immutability, source/company/job provenance, and one real public provider feed through outbox/Beat/Celery.

#### Supersedes / superseded by

None.

---

## Project decisions

### ADR-002 — Preserve Django's built-in user and add an FTL role relation

**Date:** 2026-08-05  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `06_DATABASE_SCHEMA_AND_MIGRATIONS.md`, `07_DOMAIN_STATES_AND_AUDIT_TRAIL.md`, `27_SECURITY_PRIVACY_AND_COMPLIANCE.md`  
**Related implementation:** `apps/accounts/models.py`, `apps/accounts/services.py`

#### Context

Milestone 0 applied Django's framework migrations before a custom user model existed. Swapping `AUTH_USER_MODEL` afterward would introduce unsafe migration dependencies and require invasive identity-table migration without adding product value. The normative schema requires users, roles, permissions, retained authorship, and secure access, but it does not require a bespoke authentication table.

#### Decision

Keep Django's built-in `auth.User` as the authentication identity. The `accounts` app owns an explicit one-to-one `TeamRole`, the five FTL role values, role assignment services, and idempotently seeded Django groups/permissions. All project foreign keys use `settings.AUTH_USER_MODEL` so a future evaluated identity migration remains possible.

#### Alternatives considered

- Replace `auth.User` immediately, rejected because the framework/admin migrations are already applied and the transition would create avoidable migration and data-loss risk.
- Store a free-form role directly on users, rejected because it cannot be added to the built-in model and weakens policy validation.
- Use groups alone, rejected because the product needs one canonical mutually exclusive FTL role that is easy to audit and display.

#### Consequences

Authentication remains standard Django, Argon2 remains preferred, and historical user references survive deactivation. Role assignment must synchronize the canonical `TeamRole` to its corresponding group transactionally. A future custom-user change requires a dedicated expand/migrate/contract plan rather than editing applied migrations.

#### Validation

Test all five seeded roles, permission boundaries, idempotent bootstrap, role reassignment/group synchronization, historical authorship after deactivation, and fresh/existing database migration paths.

#### Supersedes / superseded by

None.

### ADR-003 — Claim outbox rows transactionally and publish after releasing locks

**Date:** 2026-08-05  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `02_SYSTEM_ARCHITECTURE_AND_DATA_FLOW.md`, `06_DATABASE_SCHEMA_AND_MIGRATIONS.md`, `24_CELERY_ORCHESTRATION_AND_SCHEDULING.md`  
**Related implementation:** `apps/operations/outbox.py`

#### Context

The dispatcher must use `FOR UPDATE SKIP LOCKED` for concurrent claims, but holding database locks across a broker network call increases contention and makes recovery less explicit.

#### Decision

Claim a bounded batch in one short transaction by setting `status=publishing`, `claimed_by`, `claimed_at`, and incrementing attempts. Release locks before publishing. A successful publish updates only a row still owned by that claim; failure stores a safe error and retry time. A recovery service returns stale claims to eligibility. The interval after broker acceptance but before database acknowledgement intentionally permits duplicate messages, and consumers enforce idempotent effects from the outbox/envelope key.

#### Alternatives considered

- Publish while retaining the row lock, rejected because broker latency or outage would unnecessarily hold database locks.
- Publish from `transaction.on_commit()`, rejected because a process crash after commit loses the command.
- Mark published before broker acceptance, rejected because a broker failure would lose the command.

#### Consequences

At-least-once delivery is explicit. Claim ownership and stale recovery are observable, while domain effects require unique idempotency keys and short transactions. The dispatcher never treats Redis/Celery state as canonical.

#### Validation

Test concurrent claim exclusion on PostgreSQL, broker failure durability/backoff, stale recovery, ownership mismatch, publish-before-ack replay, and duplicate consumer delivery with one domain step/audit effect.

#### Supersedes / superseded by

None.

### ADR-001 — Use the current stable Redis 8 release as the milestone 0 broker

**Date:** 2026-08-05  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `04_DOCKER_LOCAL_DEVELOPMENT.md`, `24_CELERY_ORCHESTRATION_AND_SCHEDULING.md`, `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`  
**Related implementation:** `compose.yaml`

#### Context

The audited subsystem document names `redis:8.10.0-alpine`, but the official image registry currently publishes Redis 8.10 only as a release candidate. Redis 8.8.1 is the current stable Redis 8 image. The binding architecture requires a current Redis-compatible broker and does not require an unreleased broker patch.

#### Decision

Use the exact stable `redis:8.8.1-alpine` image for milestone 0. Keep Redis as disposable transport/cache only and PostgreSQL as canonical state. Reassess the exact patch through the normal dependency update gate when Redis 8.10 stable exists.

#### Alternatives considered

- Use the `8.10-rc2` image, rejected because a release candidate is inappropriate for the reviewed foundation.
- Use a floating `redis:8-alpine` tag, rejected because the milestone requires exact reviewed patch pins.
- Use Valkey, valid architecturally but unnecessary while the reviewed stable Redis line satisfies Celery transport needs.

#### Consequences

The runtime remains within the binding Redis-compatible-broker architecture while differing from the non-binding unreleased patch example. Future patch upgrades require Compose validation and the full test suite.

#### Validation

Build and start the Docker stack on ARM64, verify Redis health, run a Celery worker against it, and validate base/development/production Compose output.

#### Supersedes / superseded by

None.

### ADR-004 — Version Celery exchange names independently from queue names

**Date:** 2026-08-05  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `24_CELERY_ORCHESTRATION_AND_SCHEDULING.md`, `26_OBSERVABILITY_AND_OPERATIONS.md`  
**Related implementation:** `domain/queues.py`, `config/settings/base.py`, `apps/operations/outbox.py`

#### Context

The first live milestone 1 command reached its idempotent consumer ten times even though the outbox recorded one publication attempt. Inspection showed that Redis retained obsolete milestone 0 bindings from the period when every core queue inherited the default `maintenance` exchange. Redis transport is disposable, but deleting its persistent state is prohibited in this run and would not make future topology changes self-contained.

#### Decision

Use versioned direct exchanges named `ftl.v1.<queue>` while preserving stable queue names and routing keys. Publishers specify the declared queue only and let Celery resolve its reviewed exchange/routing policy. A future incompatible binding change advances the exchange namespace rather than relying on destructive broker cleanup.

#### Alternatives considered

- Delete Redis binding keys or the broker volume, rejected because destructive action is not authorized and transport migration should not depend on manual cleanup.
- Keep unversioned exchanges and add a startup unbind routine, rejected because the application should not mutate broker internals and could race active workers.
- Accept repeated delivery indefinitely, rejected because idempotency protects correctness but does not excuse avoidable load and misleading operational noise.

#### Consequences

Existing stale bindings remain harmless and unreachable. Queue names remain stable for workers and operations. At-least-once/idempotent handling is still mandatory because publication acknowledgement failures can legitimately duplicate messages.

#### Validation

Restart workers and Beat without clearing Redis, publish a new checkpoint through the outbox, verify one broker receipt and one domain effect, and keep the duplicate-delivery unit/integration tests.

#### Supersedes / superseded by

None.

### ADR-005 — Pin validated source addresses below HTTPX while retaining hostname TLS

**Date:** 2026-08-06  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `09_SOURCE_CONNECTORS_AND_FETCHING.md`, `27_SECURITY_PRIVACY_AND_COMPLIANCE.md`  
**Related implementation:** `apps/sources/http.py`, `apps/sources/policy.py`, `apps/sources/models.py`

#### Context

A string-only DNS check followed by a normal HTTP client connection permits a second resolver lookup and therefore a DNS-rebinding gap. Rewriting an HTTPS request to a numeric IP would break the original Host header and TLS server-name verification. Raw bodies must also remain outside ordinary relational/API paths while retaining durable provenance.

#### Decision

Use one HTTPX adapter backed by the public httpcore network-backend interface. Each request and redirect resolves through the controlled policy, rejects the entire answer set if any destination is prohibited, and gives the transport only approved IP addresses. The request URL, Host header, and TLS SNI remain the canonical hostname. HTTPX automatic redirects, environmental proxies, cookies, and automatic retries remain disabled. Persist accepted raw bodies through Django storage under deterministic endpoint/content-hash keys; PostgreSQL stores the attempt, artifact/snapshot metadata, hash, storage key, and audit/run state. PostgreSQL triggers reject artifact and snapshot update/delete.

#### Alternatives considered

- Validate DNS and then use the default HTTPX transport, rejected because the connection can perform a new unbound resolution.
- Replace the URL hostname with the validated IP, rejected because correct TLS/Host handling becomes fragile and redirect semantics become misleading.
- Store raw bodies in PostgreSQL, rejected because the audited architecture requires storage abstraction for large immutable artifacts.
- Trust HTTP redirects automatically, rejected because every hop must receive full network-policy validation.

#### Consequences

All source egress has one reviewed path and preserves hostname certificate verification without trusting a second resolver decision. The transport is intentionally HTTP/1.1-only in this slice and establishes a fresh one-connection pool per validated hop; later performance work may pool only if it preserves the same address/hostname binding. PostgreSQL backups retain complete metadata and media backups retain bodies; both are required for a full restore.

#### Validation

Cover IDNA, IPv4/IPv6, decimal/octal/hex-like resolver results, mixed DNS, metadata/CGNAT/multicast/reserved ranges, redirect-to-private, address pinning, media/byte limits, conditional requests, retries, immutable storage, PostgreSQL triggers, live HTTPS fetching, and isolated backup restore.

#### Supersedes / superseded by

None.


### ADR-007 — Allow multiple immutable normalizations of one raw source snapshot

**Date:** 2026-08-06  
**Status:** accepted  
**Owners:** FTL engineering  
**Related specifications:** `06_DATABASE_SCHEMA_AND_MIGRATIONS.md`, `10_NORMALIZATION_SNAPSHOTS_DEDUPLICATION.md`  
**Related implementation:** `apps/jobs/models.py`, `apps/jobs/services.py`, `apps/jobs/migrations/0005_remove_jobpostingsnapshot_jobs_snapshot_source_posting_connector_unique.py`

#### Context

An HTTP 304 correctly reuses an immutable raw source snapshot. A new normalizer version may nevertheless produce a different normalized hash from that same artifact. The original uniqueness constraint on `(source_snapshot, posting, connector_version)` rejected this valid append-only upgrade even though `(posting, full_hash)` already protects identical normalized content.

#### Decision

Keep raw artifacts/snapshots and normalized snapshots immutable, but allow multiple normalized snapshots to reference one raw snapshot. Canonical uniqueness is `(posting, full_hash)`. Normalizer version is included in the full hash and visible change diff; poll observations remain unique per `(posting, fetch_attempt)`.

#### Alternatives considered

- Mutate the prior normalized snapshot, rejected because normalized history is append-only.
- Create a duplicate raw snapshot for HTTP 304/reprocessing, rejected because the body was not re-retrieved and raw provenance would become false.
- Retain the three-column constraint and ignore normalizer upgrades, rejected because changed normalization could not be persisted or audited.

#### Consequences

Normalizer upgrades may create a cosmetic or material event according to semantic/diff policy while retaining the same raw artifact. Reprocessing mode can append a new normalized version without inventing another source retrieval. Constraint errors fail visibly through the durable parse run.

#### Validation

Re-poll an existing real Ashby source through HTTP 304 after upgrading normalizer v1.0.0→v1.1.0; verify 56 new observations/events and snapshots, no duplicate postings, completed durable runs, and PostgreSQL immutability triggers.

#### Supersedes / superseded by

None.


## 2026-08-05 — Knowledge-base release 2.1 audit

- Current extended research defaults to capability-tested GPT-5.6 reasoning models plus `web_search`; deprecated dedicated deep-research policies are disabled by default.
- Background Mode/ZDR is modeled as a provider capability with `store=false` support and a short reverified retrieval window, not a categorical incompatibility.
- Contact routes now record public versus human origin; public extraction cannot infer warm introductions or existing relationships.
- Outreach is represented as exact-bound content units and rendered deterministically before review/approval.

### ADR-008 — Keep one Caddy edge while isolating the public website

**Date:** 2026-08-11
**Status:** accepted
**Owners:** FTL engineering
**Related specifications:** `04_DOCKER_LOCAL_DEVELOPMENT.md`, `26_OBSERVABILITY_AND_OPERATIONS.md`, `29_BACKUP_RESTORE_AND_SERVER_MIGRATION.md`
**Related implementation:** `compose.prod.yaml`, `docker/Caddyfile.prod`

#### Context

The production host already has one healthy Caddy container with durable certificate volumes and exclusive ownership of ports 80/443 for `opportunities.ftl.vision`. The new public website is a separate portable Docker application and must not gain access to the customer platform's database, broker, workers, or private application network.

#### Decision

Retain the existing Caddy container as the only public edge. Add an external Docker network named `ftl-edge`; attach only Caddy and the public website to it. Caddy remains attached to `backend` for the existing `web:8000` upstream. Route `ftl.vision` to `ftl-webpage:8080`, permanently redirect `www.ftl.vision` to the apex while preserving the request URI, and retain `{$PUBLIC_DOMAIN}` for the customer application.

#### Alternatives considered

- Publish a second Caddy or website port on the host, rejected because ports 80/443 already have one owner and duplicate edge/certificate state increases operational risk.
- Attach the website to `backend`, rejected because the public application does not need reachability to customer-system services.
- Move the customer application behind the website's Compose project, rejected because website releases and rollbacks must not control customer data or workers.

#### Consequences

The two applications release independently while sharing certificates, redirects, compression, and transport headers at one reproducible edge. A routine website rollback recreates only the website container. Caddy remains a shared dependency and its configuration is validated before a proxy-only recreation.

#### Validation

Render all production Compose layers, validate the Caddyfile inside the pinned Caddy image, verify website readiness over `ftl-edge`, verify both homepage certificates and the `www` redirect, and confirm `opportunities.ftl.vision` before and after the edge change.

#### Supersedes / superseded by

None.
