# Implementation Status

**Status:** Milestone 11 verified; HOFFMANN creative-learning discovery refinement verified in production; shared Caddy edge prepared for the public FTL website
**Knowledge-base release:** 2.1 (audited)  
**Completed milestone:** 11 — Buyer roles and public/human contact routes  
**Next in-scope milestone:** 13 — Selective deep research (milestone 12 drafting is deferred by user request)  
**Last updated:** 2026-08-11

## Verified software

- Milestone 0's pinned Python 3.13.14/Django 5.2.17/PostgreSQL 18.4/Celery 5.6.3/Redis 8.8.1 foundation, private base data services, explicit release migration, typed configuration, health checks, and backup/restore controls remain intact.
- Django authentication plus one canonical `TeamRole` per retained user; five idempotently seeded role groups and permission policies; audited transactional role assignment.
- `PipelineRun`, unique `PipelineStepRun`, `TaskOutbox`, `ProviderCall`, and append-only `AuditEvent` models with additive migrations, constraints, operational indexes, and PostgreSQL update/delete rejection for audits.
- Strict Pydantic v2 checkpoint/envelope contracts carrying IDs and bounded scalars only; atomic run/audit/outbox creation; bounded PostgreSQL `SKIP LOCKED` claims; publish outside row locks; safe errors, retry/backoff, stale-claim recovery, manual audited retry, and exactly-once domain effects under duplicate task delivery.
- JSON-only Celery messages, disabled result backend, late acknowledgements, explicit queue policy, versioned direct exchanges, a ten-second outbox dispatcher, and a sixty-second stale-claim recovery schedule.
- Authenticated overview, pipeline run, outbox, audit, retry, and detailed dependency-health pages with explicit permissions, CSRF-protected POST actions, request correlation, safe status detail, and no raw fetched/provider content.
- Restrained dark responsive UI with semantic structure, visible focus, status text/shapes, reduced-motion handling, and immutable WhiteNoise static assets included in the shared runtime image.
- CSP, clickjacking, CSRF, secure production cookies, Argon2, allowlisted structured logging, redaction, writable-storage readiness, and provider/outreach feature gates remain fail-closed.
- Canonical/provisional companies with multiple verified/unverified domains, reviewed aliases, explicit merge-review records, and no name-only or ATS-host auto-merge.
- Public source candidate and endpoint registration, strict typed submission/fetch contracts, immediate submission-time policy rejection, transactional candidate/run/audit/outbox creation, and an ID-only `fetch` queue task.
- One reviewed HTTPX/httpcore egress adapter with HTTPS/port/userinfo policy, IDNA, controlled DNS, every-answer public-address validation, validated-address TCP pinning with hostname TLS, manual redirect revalidation, no ambient credentials/proxies/cookies, conditional requests, content/byte/time bounds, and safe failure taxonomy.
- Durable `FetchAttempt` history plus storage-backed immutable `SourceArtifact` and `SourceSnapshot` provenance. PostgreSQL triggers reject artifact/snapshot updates and deletes; no UI/API path renders raw fetched HTML.
- Authenticated source and company registry/detail pages with owner, status, policy, freshness, hashes, attempts, run/audit correlation, safe errors, and role/CSRF enforcement.
- Deterministic Personio XML, Greenhouse JSON, Lever JSON, Ashby JSON, JobPosting JSON-LD, and conservative generic-HTML connectors behind one strict, versioned Pydantic boundary. XML DTD/entities/external references, excessive JSON nesting/items/text, ambiguous content, and known-provider schema drift fail visibly without fallback.
- Canonical `JobPosting` and ordered `JobLocation` state plus append-only `JobPostingSnapshot`, exact `PostingObservation`, and durable `ConnectorParseAttempt` history. PostgreSQL rejects normalized-snapshot update/delete and current posting pointers remain queryable.
- Changed source snapshots atomically create a separate `jobs.normalization` run and `jobs.parse` outbox command. The `parse` worker verifies storage size and SHA-256 before parsing; duplicate task delivery/content is idempotent and a 304/unchanged snapshot creates no parse command.
- Authenticated job list/detail plus company/source cross-links expose provider identity, freshness, locations, normalized content, source artifact, parse run, immutable hashes, and observations without exposing raw source bodies.
- Exact successful-poll observations now use fetch-attempt identity even when an immutable raw snapshot is reused after HTTP 304 or identical content. Complete documented provider collections may be empty and still advance deterministic absence policy; failed/invalid/partial sources never count.
- Canonical postings retain normalized title, absence counter, closure timestamp/reason, and audited open/closed state. Two consecutive complete successful absences close; explicit provider state closes immediately; supported reappearance reopens and resets absence.
- Append-only `PostingChangeEvent` records created/unchanged/cosmetic/material/closed/reopened transitions with old/new snapshots, exact changed fields, hashes, policy, observation, parse run, and idempotency. PostgreSQL rejects update/delete.
- Non-destructive `DuplicateRelationship` records exact canonical-URL or verified-company semantic matches without merging/deleting either posting. Posting pages expose deterministic diffs, lifecycle history, duplicate context, absence state, and immutable snapshots.
- Normalizer policy is v1.1.0. Multiple immutable normalizations may validly derive from the same immutable raw snapshot; uniqueness remains posting/full-hash. Constraint failures fail visibly and never leave a false completed run.
- Immutable-version `SearchDefinition` records, logical-window-idempotent `DiscoveryRun`/`DiscoveryQuery` records, strict candidate provenance, watched endpoints, durable PostgreSQL execution leases, and daily 06:00 Europe/Berlin scheduling are operational.
- Discovery prompt/policy v2.2.0 separates DACH creative-video and learning-enablement families plus a focused Munich intent shard from the existing operations query, searches German and English role/task language, and automatically watches each safely registered active endpoint. Signal detector/ontology v1.1.0 recognizes exact German creative-video and learning-content evidence without employer-specific rules.
- Manual or scheduled discovery first writes its run, audit event, and `discovery.execute` outbox command atomically. Known endpoints create ordinary ID-only source-ingestion commands and reuse the same SSRF-safe fetch, immutable artifact, deterministic parse, lifecycle, and change-event path.
- The central typed OpenAI Responses adapter uses the current `web_search` tool and strict Pydantic Structured Outputs behind immutable capability/model policies. Response IDs, usage/tool/source metadata, retention, failures, and bounds are durable; model/tool syntax is absent from discovery business services.
- Per-run, stage daily/monthly, account daily/monthly, and concurrency limits are enforced before provider egress using conservative maximum-cost reservations. Refusal, incomplete, schema/catalog-reference, policy, budget, rate, and provider failures remain explicit and fail only the optional provider path.
- Discovery definitions, runs, queries, candidates, downstream source state, warnings, and safe errors are visible in the authenticated workspace. Search snippets are labeled diagnostic and are structurally isolated from future evidence tables.
- Eligible created/material/reopened/closed posting events now transactionally queue ID-only `signals.detect` commands on `classification`. Each run has a durable detection attempt, step, terminal signal/no-signal/failure state, input hash, policy versions, and append-only audit correlation.
- Exact `EvidenceCatalog`/`EvidenceItem` records are deterministically built only from immutable normalized job snapshots. Stable `EV-` IDs, exact text, normalized text, offsets, language, content/catalog hashes, and builder version are in PostgreSQL; PostgreSQL triggers reject catalog/item update and deletion.
- Versioned deterministic signal ontology/detector policy recognizes bounded capability phrases in English/German with token boundaries, excludes instruction-like source segments, and treats generic `AI` as no signal. Strict `SignalDetectionResultV2` uses the canonical required keys and rejects extra keys, invalid IDs/tags, wrong event kinds/snapshots, duplicate references, and commercial rationale.
- `SignalEvent` and append-only `SignalEvidence` preserve observed action separately from later inference. A newer successful detector policy atomically supersedes prior active results without deletion and records system audits; reviewer false-positive retraction preserves evidence and requires an audited reason.
- The authenticated Signal Inbox defaults to active results and exposes company/job/source/run links, exact quotes, offsets, hashes, freshness, confidence, detector/prompt/schema/ontology versions, claim boundary, and retraction state. Company and job pages cross-link their signals.
- Current active signals automatically queue deterministic capability classification through the outbox. Strict `CapabilityAssessmentV2` output records clusters, plausible gaps, exactly one opportunity mode, FTL layers, component judgments, unknowns, and evidence references; Python alone computes the final relevance score and coverage.
- `SignalAssessment`, normalized cluster/gap/evidence links, separate actor/reason mode overrides, and policy/version/input hashes preserve classification history. PostgreSQL triggers reject assessment-evidence link mutation.
- Current completed signal assessments automatically queue time-bounded company aggregation. Every required temporal/source/role/capability feature is persisted with cutoff, input IDs/hash, and builder version; pattern inference remains separate from observed `SignalEvent` facts.
- Company score history exposes capability relevance, commercial actionability, long-term system potential, strategic value, priority, per-component/overall coverage, and explicit missing fields. Unknown values are not zero; the configured normalized-known-weight coverage penalty is reproducible in Python.
- One active opportunity per company/use-case family links all supporting signals and keeps qualification, research, solution, outreach, and relationship states independent. Mode and qualification overrides remain audited separate records; signal retraction queues re-aggregation and deactivates unsupported current opportunities without deleting history.
- The authenticated opportunity ranking/detail workspace exposes score decomposition, coverage, features, patterns, source-linked signals, freshness cutoff, versions, missing inputs, status, next action, and review controls. Company/signal pages cross-link assessments and opportunities.
- Standard company research uses one typed Responses provider boundary with a cited public-web report pass and a separate no-web strict extraction pass. Active immutable policies own model, tool, reasoning, limits, budget, and `store=false`; response IDs, usage/tool/source metadata, safe failures, and provider-call state are durable.
- `ResearchRun`, immutable storage-backed `ResearchReportArtifact`, provider-derived `ResearchSource`, evidence-bound `ResearchClaim` plus source/signal/evidence links, and deterministic `ResearchDossier` records retain hashes, versions, freshness, partial failure, and current/history state in PostgreSQL. Database triggers reject mutation/deletion of evidence records.
- Eligible research requests atomically create an ID-only durable outbox command; public context excludes private FTL/CRM/solution state. Python registers/normalizes URLs into local `SRC-` IDs before a no-web extraction may reference them, rejects fabricated IDs and research-stage boundary crossings, assigns local `CLM-` IDs, and advances only the independent opportunity research status.
- The authenticated research list/detail and opportunity research panel expose status, source URLs/types/retrieval/citations, claims/evidence, integrity hashes, policies, pipeline, partial failures, cited report, and canonical dossier as escaped plain text. Live calls remain fail-closed behind three feature flags, a credential, active policies, and budgets.
- Immutable knowledge releases store exact source commit/manifest hashes plus offers, approved/prohibited claims, and assets. Strict Pydantic catalogs, bounded local path reads, URL policy, cross-reference validation, append-only database triggers, and separate audited activation prevent an editorial sync from silently changing active business logic.
- Immutable evidence-bound solution versions store exact opportunity, research, knowledge, prompt/schema/input/output hashes, phased design, gates, assumptions, risks, unknowns, and buyer-role responsibilities. Structured edits append a new version; human approval binds the exact version and output hash.
- Asset matching first excludes non-public, externally unapproved, confidential, embargoed, wrong-audience/language, stale-review, or stale-link candidates in Python. The deterministic downstream match selects zero to two records from the active release and records explicit exclusion reasons; zero assets is valid and never causes invention.
- Solution design and matching use ID-only durable outbox commands on dedicated queues with replay-safe effects and visible pipeline/audit state. Research or active-knowledge changes make dependent current outputs stale while preserving all historical versions.
- The authenticated knowledge and solution workspaces expose release/activation provenance, offers/claims/assets, phases, evidence bindings, validity/freshness, selected/excluded assets, status, versions, and audit context. Email generation, approval, and sending are absent by design.
- Approved exact solutions with completed asset matching can queue deterministic buyer-role inference. Immutable role hypotheses bind only supplied solution responsibilities and research claim/source/evidence IDs; they never assert a named person, reporting line, or contact route.
- Contact scans are bounded to registered official-company research sources on the known company registrable domain and reuse the SSRF-safe, address-pinned HTTP adapter. Only literal public `mailto:`, `tel:`, form-action, and contact-link observations survive inactive/executable-markup removal; no guessed address or inferred human relationship is permitted, and zero routes is valid.
- Contact-source bodies, sensitive evidence fragments, and protected route values are authenticated-encrypted before Django storage/PostgreSQL persistence. Separate keyed HMAC fingerprints support deduplication and synchronous suppression; immutable evidence retains hashes, exact offsets, source, retrieval, parser, and key-version provenance without exposing protected plaintext.
- Public versus human origin, observation, freshness, deliverability, outreach eligibility, legal review, recommendation, suppression, and selection are independent. Human routes require actor/provenance; an exact route can be selected only after human eligibility/legal approval and a synchronous suppression check. The authenticated contact workspace exposes masked provenance and audit state while creating no packet, draft, email, or send.

## Executed checkpoint evidence

### Public website shared-edge integration

- The production Caddy proxy remains the only service that publishes ports 80/443 and retains its existing certificate volumes.
- The proxy joins the existing private `backend` network and the external `ftl-edge` network. PostgreSQL, Redis, Django, Celery workers, and Beat remain on `backend` only.
- The production Caddyfile adds `ftl.vision`, a permanent path/query-preserving `www.ftl.vision` redirect, and keeps `{$PUBLIC_DOMAIN}` routed to `web:8000`.
- The public website supplies its own nonce-based route CSP; the shared edge supplies transport and common security headers.
- Validation consists of rendered Compose policy checks, Caddy configuration validation, homepage readiness over `ftl-edge`, TLS/redirect probes for both homepage names, and an immediate regression probe for `opportunities.ftl.vision`.

### Milestone 5 production refinement — local verification

- Focused Docker verification passed 28 discovery/provider/signal/auth/integration/E2E tests. The neutral German creative-learning fixture produces both required capability tags and the rendered query includes Munich/München, part-time/student terms, and exact creative/learning task vocabulary without a company name.
- Final aggregate `make verify` exited 0: 295 files were formatted/Ruff clean; strict mypy passed across 220 source files; migration drift and deployment checks passed; 161 unit tests passed at 80.10% coverage; 14 PostgreSQL integration tests and 10 real-HTTP E2E tests passed; Compose, document-link, and secret gates were clean.
- Production run `91d93764-1fd5-4b36-8f65-111ceba12ba0` made one bounded live OpenAI web-search call and completed with six first-party candidates, six accepted registrations, no unsafe candidates, and eight known endpoints queued. The result omitted HOFFMANN EITLE and exposed intent dilution in the combined creative+learning+tools query.
- Production run `1ace06cf-0a92-40f6-9157-c7d77706aeac` tested the narrower creative family and returned four candidates, including first-party LUMAS and zooplus roles, but completed partial after reaching its tool limit and still omitted HOFFMANN EITLE.
- The final local correction adds a Munich/München intent shard and prompt/policy v2.2.0, which begins with employer-site task/location searches and prevents preferred ATS domains from consuming the search as mandatory filters. Focused verification passed 18 tests; final `make verify` passed with 296 formatted/Ruff-clean files, strict mypy across 220 source files, 161 unit tests at 80.11%, 14 integration tests, 10 E2E tests, and clean migration/deploy/Compose/docs/secrets gates. No migration is required; deployment and a bounded Munich run remain pending.
- Production Munich run `6b22f900-35a1-4605-b33e-9f66ef4267ec` completed with five accepted first-party candidates, no unsafe candidates, and HOFFMANN EITLE as the first result. The safe HTTP fetch returned 200 and stored one immutable source snapshot.
- The HOFFMANN Personio URL is a single-job HTML page with strict `JobPosting` JSON-LD, not an XML collection. Content-aware connector routing now selects JSON-LD before the Personio hostname fallback while preserving explicit/known API fail-closed behavior. The production reparse persisted the canonical posting, and a regression-tested lifecycle correction now records `created` when a reparse creates the first posting so signal continuation is not lost.
- Final aggregate `make verify` exited 0: 296 files were formatting/Ruff clean; strict mypy passed across 220 source files; migration drift and production deployment checks passed; 163 unit tests passed at 80.17% coverage; 14 PostgreSQL integration tests and 10 real-HTTP E2E tests passed; Compose, document-link, and secret gates were clean.
- Production is healthy on image `ftl-opportunity-intelligence:git-cbc14143d2419b2823dbbf7b476a7cdd4b1db847`; the explicit release operation found no pending migrations and readiness returned HTTP 200. HOFFMANN EITLE has an open canonical job, a completed detection attempt, one active 0.950-confidence capability-hiring signal tagged `creative_ai_production` and `learning_content`, a completed deterministic assessment, and an active `research_eligible` opportunity with priority 56 and 0.670 score coverage. All related outbox commands completed.

### Milestone 11

- Additive migrations `contacts` 0001–0002 were applied once through the rebuilt release image; idempotent platform bootstrap updated all five role policies. PostgreSQL 18 triggers reject mutation/deletion of immutable buyer-role and contact-evidence records.
- Final aggregate `make verify` exited 0: 294 files were formatted/Ruff clean; strict mypy passed across 220 source files; migration drift and production deployment checks passed; `make test` passed 158 tests at 80.06% coverage; `make test-integration` passed 14 PostgreSQL tests; `make test-e2e` passed 10 real-HTTP tests; Compose, document-link, and secret gates were clean.
- Deterministic fixtures cover approved-solution preconditions, exact role/evidence binding, company-domain source restriction, literal route extraction, hostile-script removal, guessed-address rejection, encrypted artifact/evidence/route storage, separate HMAC lookup, human-origin restrictions, independent review, synchronous suppression, exact selection, replay, permissions, PostgreSQL immutability, and authenticated masked rendering.
- Live OpenAI calls and live contact-source scans were intentionally skipped. Separate encryption/HMAC keys were generated without disclosure and contact scanning is enabled in the retained local development runtime; a fresh `make bootstrap` generates the same independent keys securely.

### Milestone 10

- Additive migrations `knowledge` 0001–0002 and `solutions` 0001–0002 were applied once through the rebuilt release image; idempotent platform bootstrap updated all five role policies. PostgreSQL immutability triggers passed against the real PostgreSQL 18 service.
- Focused deterministic tests passed: 5 service/contract tests, 1 PostgreSQL trigger test, and 1 authenticated real-HTTP knowledge/asset/solution flow. Invalid catalogs, confidential assets, fabricated evidence, sync/activation separation, valid zero-asset matching, exact approval, and replay are covered without provider egress.
- Complete Docker regression suites passed before the final aggregate gate: `make test` 151 passed at 80.18% coverage; `make test-integration` 13 passed; `make test-e2e` 9 passed. Migration drift was clean and strict mypy passed across 208 source files.
- Live OpenAI calls were intentionally skipped. The starter editorial files contain one reviewed offer module and empty approved-claim, prohibited-claim, and asset lists; no FTL claim or collateral was invented.

### Milestone 9

- Docker checkpoint commands passed: migration drift clean; `make test` 146 passed at 81.14% coverage; `make test-integration` 12 PostgreSQL tests passed; `make test-e2e` 8 real-HTTP tests passed.
- Additive migrations `opportunities` 0003 and `research` 0001–0002 were applied once through the rebuilt release image, followed by idempotent role/model-policy bootstrap.
- Deterministic provider fixtures completed the public report → source registry → no-web extraction → claims/dossier path. Tests prove current SDK call separation, private-context isolation, invalid-source rejection, partial report preservation, replay safety, PostgreSQL append-only enforcement, and authenticated real-HTTP rendering.
- Live OpenAI calls were intentionally skipped because the runtime credential/feature flags were not authorized. No live Hostinger research run was queued, so the existing opportunity remains safely research eligible.

### Milestones 7–8

- Checkpoint Docker commands passed: migration drift clean; `make test` 142 passed at 81.50% coverage; `make test-integration` 11 PostgreSQL tests passed; `make test-e2e` 7 real-HTTP tests passed.
- Additive migrations `signals` 0004–0005 and `opportunities` 0001–0002 are applied once through the rebuilt release image. Idempotent platform bootstrap seeded the new read/override permissions.
- The live Hostinger dataset produced five completed signal assessments, five appended company assessments (one current, four superseded), and one active research-eligible opportunity through ordinary outbox/worker processing. Current score is 71 with 0.670 coverage and four deterministic patterns across five linked signals.
- Browser QA confirmed the active ranking and detail workspace, including independent states, score coverage/components, missing vendor/contact/partnership/strategic inputs, all deterministic feature rows, pattern support, source job links, and next action `company_research`.
- Live OpenAI calls were intentionally skipped; classification and aggregation are deterministic and provider independent.

### Milestone 6

- Final aggregate `make verify`: exit 0. Formatting/Ruff were clean across 205 files; strict mypy passed across 149 source files; migration drift and production deployment checks passed.
- `make test`: 138 unit tests passed at 82.36% coverage. Deterministic fixtures cover exact offsets/hashes, English/German capability terms, generic-AI and token-substring no-signal outcomes, injection-like text exclusion, invalid evidence/commercial rationale rejection, replay, policy supersession, role boundaries, and audited retraction.
- `make test-integration`: 10 PostgreSQL tests passed, including evidence catalog/item and signal-evidence trigger enforcement plus the existing outbox/source/job constraints. `make test-e2e`: 6 real-HTTP tests passed, including authenticated signal provenance.
- Base/development/production Compose policy, local document links, and secret scanning passed. Five additive migrations (`jobs` 0006–0007 and `signals` 0001–0003) are applied.
- Live public Hostinger Ashby ingestion `847b8b4c-f3a8-4bfe-9fa1-9a8785ea0f34`: HTTP fetch and parse completed through the ordinary outbox/workers, creating 72 canonical jobs and 72 eligible created events. Current detector/ontology 1.0.2 produced 72 catalogs, 553 evidence items, 67 explicit no-signal outcomes, and 5 active capability-hiring signals.
- A browser review exposed and the tests now guard an `etl`-inside-`quietly` substring false positive. Token-boundary policy 1.0.2 reprocessed all events, superseded 15 results from the two earlier smoke policies with durable audits, and left only the current five active results.
- Browser QA verified the active-only inbox, semantic table/filter controls, source-exact quote with literal matched phrase, offsets/hash, job/company/artifact/run navigation, claim boundary, and version visibility.

### Milestone 5

- Final aggregate `make verify`: exit 0 after a secret-scanner fixture annotation was corrected and the complete gate was rerun.
- `make lint`: 182 files formatted and Ruff clean. `make typecheck`: no issues in 131 Django/Pydantic source files. Migration drift and production deployment checks passed.
- `make test`: 126 unit tests passed at 83.37% coverage. Tests cover version/window idempotency, strict candidates, unsafe/duplicate handling, catalog-reference validation, disabled-provider execution, budget blocking before API invocation, current SDK request shape, lease exclusion, roles, and UI actions.
- `make test-integration`: 8 PostgreSQL tests passed, including one-active-definition constraint enforcement. `make test-e2e`: 5 real-HTTP tests passed, including authenticated discovery queueing.
- Base/development/production Compose rendering, local document links, and implementation-file secret scanning passed.
- Four additive migrations (`discovery` 0001–0002 and `providers` 0001–0002) are applied. Bootstrap now seeds five roles, three database-backed Beat schedules, one versioned definition, one reviewed disabled-by-feature policy, and watches for active endpoints.
- Live manual discovery `a3a260d0-6249-45db-bbf0-950efdf8bec7`: run/outbox completed/published, three watched endpoints queued, and `web_search_disabled` remained explicit. Ashby completed through HTTP 304 with no duplicate job; example.com completed; the oversized legacy OpenAI board failed safely as `FETCH_RESPONSE_TOO_LARGE` with no posting/lifecycle side effect.
- Browser QA verified semantic definition/run tables, manual action, watched-endpoint/candidate metrics, warning visibility, pipeline linkage, source-hint isolation, keyboard landmarks, and the candidate-provenance workspace.

### Milestone 4

- Final aggregate `make verify`: exit 0 after every quality target.
- `make lint`: 151 files formatted and Ruff clean. `make typecheck`: no issues in 106 source files. Migration drift and production deploy checks passed.
- `make test`: 118 unit tests passed at 83.79% coverage. Sequence tests cover created/cosmetic/material, two-poll closure, reopen, invalid-parse non-closure, duplicate preservation, empty complete feeds, identical snapshot reuse, and envelope replay.
- `make test-integration`: 7 PostgreSQL tests passed, including normalized-snapshot and posting-change-event trigger enforcement. `make test-e2e`: 4 real-HTTP tests passed.
- Compose configuration, documentation links, and secret scanning passed.
- Five jobs migrations are applied. The fifth removes an over-restrictive source-snapshot/posting/connector uniqueness constraint so a newer normalizer can append a new immutable normalization of the same raw source.
- Live Ashby `sources.live:m4-ashby-repoll-20260806`: HTTP 304, source run complete, normalization run complete after verified recovery, 56 new observations, 56 cosmetic v1.0.0→v1.1.0 events, 56 postings, and 112 immutable normalized snapshots.
- A deliberately submitted OpenAI Ashby feed exceeded the configured response limit and failed safely as `FETCH_RESPONSE_TOO_LARGE`; it produced no posting, observation, or lifecycle side effect.
- Browser QA verified the exact change timeline, old/new normalizer values, updated last-seen time, absence/closed fields, duplicate section, immutable history, and raw-source isolation.

### Milestone 3

- Final aggregate `make verify`: exit 0 after all quality targets (following removal of a secret-scanner false-positive fixture identifier).
- `make lint`: exit 0; 148 files formatted and Ruff clean. `make typecheck`: exit 0; strict Django-aware mypy reported no issues in 103 source files.
- `make check-migrations`: exit 0; `No changes detected`. Two additive jobs migrations were applied, bringing the live database to 48 migration records. `make check-deploy`: no issues.
- `make test`: 113 unit tests passed, 10 integration/E2E tests deselected, 84.18% branch coverage. All six connector fixture families, unsafe markup removal, XML entity rejection, strict failure, durable normalization, failure visibility, replay idempotency, permissions, and UI provenance passed.
- `make test-integration`: 6 PostgreSQL tests passed, including normalized-snapshot immutability. `make test-e2e`: 4 real-HTTP tests passed, including authenticated canonical-job provenance.
- Compose, document-link, and secret gates passed. The secret scanner correctly stopped on a synthetic fixture identifier during an earlier aggregate run; the identifier was removed and the gate rerun cleanly.
- Live source `sources.live:m3-ashby-20260806`: HTTP 200, 1,651,322-byte immutable artifact, one source snapshot, successful `ashby` connector v1.0.0 run, 56 canonical open postings, 381 locations, 56 immutable normalized snapshots, and 56 observations; no errors.
- Browser QA showed a legible 56-posting workspace and source-backed job detail with public posting, source endpoint, artifact metadata, parse run, hashes, and observation. No raw fetched markup was rendered.

### Milestone 2

- Final aggregate `make verify`: exit 0 after all quality targets.
- `make lint`: exit 0; 124 files formatted and Ruff clean.
- `make typecheck`: exit 0; strict Django-aware mypy reported no issues in 85 source files.
- `make check-migrations`: exit 0; `No changes detected`. Four additive company/source migrations were applied to the live database, bringing it to 46 migration records.
- `make check-deploy`: exit 0; Django production deployment checks reported no issues.
- `make test`: exit 0; 99 unit tests passed, 8 integration/E2E tests deselected, 85.20% branch coverage against the 80% floor.
- `make test-integration`: exit 0; 5 PostgreSQL tests passed, including audit and source immutability triggers, concurrent outbox claiming, broker-failure durability, and duplicate-effect idempotency.
- `make test-e2e`: exit 0; 3 live HTTP tests passed, including authenticated unsafe-source rejection without a network command.
- `make compose-config`, `make check-docs`, and `make secret-scan`: exit 0; all Compose policies, Markdown links, and implementation-file secret checks passed.
- Controlled live source fetch `sources.live:m2-example-20260806`: candidate registered; pipeline complete at `source_fetch_complete`; HTTP 200; 559 bytes; one attempt, one immutable artifact, and one source snapshot; no error code.
- Browser QA: the authenticated source submission, safe private-target rejection, candidate, endpoint, attempt, and artifact pages were semantic and visually legible; raw-body isolation was explicit; console had no warnings/errors.
- `make persistence-check`: 46 migration records survived PostgreSQL stop/recreate.
- `make backup`: created `backups/20260806T075120Z/`; `make restore-drill FILE=backups/20260806T075120Z/database.dump`: exit 0 with 46 applied migrations after isolated restore.

### Milestone 1 baseline

- `make format`: exit 0; 88 Python files unchanged and Ruff safe fixes clean.
- `make lint`: exit 0; 88 files formatted and `All checks passed!`.
- `make typecheck`: exit 0; strict Django-aware mypy reported no issues in 57 source files.
- `make check-migrations`: exit 0; `No changes detected`.
- `make check-deploy`: exit 0; Django production deployment checks reported no issues.
- `make test`: exit 0; 61 unit tests passed, 6 integration/E2E tests deselected, 89.68% branch coverage against the 80% floor.
- `make test-integration`: exit 0; 4 PostgreSQL tests passed, covering the PostgreSQL 18 runtime, audit trigger, concurrent outbox claiming, broker-failure durability, and duplicate-effect idempotency.
- `make test-e2e`: exit 0; 2 HTTP live-server tests passed, including health and static CSS delivery.
- `make compose-config`: exit 0; base, development, and production rendering/policy passed with one shared application image and private base/production data services.
- `make check-docs`: exit 0; all local Markdown links resolve.
- `make secret-scan`: exit 0; no potential secrets detected in implementation files.
- Final aggregate `make verify`: exit 0 after executing every quality target above.
- Browser QA: authenticated desktop/mobile operations flows rendered with CSS; 390 px viewport had no horizontal overflow; keyboard focus was visible; checkpoint creation reached complete/published state; console had no warnings or errors. The local fixture user was then deactivated and its password made unusable.
- Non-destructive live migration/bootstrap: 42 migrations applied, five role groups present, and both database-backed Beat schedules enabled.
- Fresh live checkpoint `219e7d5e-12d0-4f31-ace9-07f9927dfbde`: complete run, published outbox in one attempt, one worker receipt, one step effect, and one completion audit.
- Live probes: liveness 200, readiness 200 with configuration/database/migrations/storage true, and `/static/css/app.css` 200 as `text/css` through Caddy.
- Final process check: web/PostgreSQL/Redis were healthy, both Celery workers answered `pong`, Beat and Caddy were running, and the application remained available on loopback port 8000.
- `make persistence-check`: 42 migration records survived PostgreSQL stop/recreate.
- `make backup`: created `backups/20260805T155046Z/` with a 75,878-byte custom-format dump, media archive, manifest, and verified SHA-256 checksums.
- `make restore-drill FILE=backups/20260805T155046Z/database.dump`: exit 0; isolated PostgreSQL 18 restore passed with 42 migration records.

## Provider-call status

Three bounded live standard OpenAI web-search discovery calls were performed for this production refinement: the initial combined family, the split creative family, and the final Munich intent shard. No extended/deep-research call was performed. All remaining automated verification used deterministic fixtures. Signal detection/classification/scoring, solution/asset matching, and buyer-role inference remain deterministic. Public HTTPS job sources were fetched only through the safe-fetch adapter. No live contact request was submitted at this checkpoint. Email integration, reply ingestion, JavaScript-browser scraping, and first-contact sending remain disabled.

## Open work and risks

- Provider job feeds, exact lifecycle/change history, scheduled/manual discovery, immutable evidence catalogs, observed signals, classification/scoring, opportunity aggregation, standard research, versioned FTL knowledge/assets, solution/asset matching, buyer-role inference, protected official-source route scanning, review, suppression, and selection now work. Drafting and outreach remain deliberately deferred.
- Standard public-web research still requires explicitly enabling reviewed OpenAI policies and supplying a real credential; the default/offline test configuration cannot create real company dossiers. Contact scanning additionally requires separate 32-byte encryption/HMAC keys and scans only registered official sources from a completed dossier, never arbitrary or private pages.
- The starter asset catalog is intentionally empty because no reviewed FTL collateral metadata was supplied. Editors must add real public assets with review and link-health metadata, sync a new release, and explicitly activate it before those assets can be selected.
- Endpoint robots outcome remains `unknown` unless explicitly supplied. Documented public APIs are submitted intentionally, but per-registrable-domain leases/rate scheduling and automated robots classification still need enforcement before broad discovery.
- Standard web discovery improves routine recall but cannot prove completeness. Milestone 13 should add a bounded weekly/on-demand deep-research discovery audit that accepts the task/location/hours brief plus already-known companies and URLs, returns only candidate official sources, and routes every candidate through the existing safe-fetch, evidence, signal, and PostgreSQL pipeline.
- Old disposable Redis binding keys from the pre-milestone-1 queue topology remain in the local named volume because destructive cleanup was prohibited. Versioned `ftl.v1.*` exchanges isolate them; a fresh command was observed exactly once after restart. ADR-004 records the migration policy.
- Local development backups are unencrypted. Production rollout must enable encrypted backup storage and complete the server restore rehearsal in milestone 15.
- The temporary browser-QA operator is deactivated and made unusable at the final checkpoint. No real production operator, production domain, credential, or TLS certificate is provisioned.

## Next verified stopping condition

Milestone 12 (`19_SOLUTION_PACKET_AND_OUTREACH_BRIEF.md` through `21_OUTREACH_APPROVAL_AND_EMAIL_INTEGRATION.md`) is intentionally deferred because the user excluded email generation and sending. The next in-scope checkpoint is milestone 13 selective deep research using `15_EXTENDED_DEEP_RESEARCH_AGENT.md`, `24_CELERY_ORCHESTRATION_AND_SCHEDULING.md`, `25_OPENAI_CLIENT_MODEL_ROUTING_AND_COSTS.md`, `26_OBSERVABILITY_AND_OPERATIONS.md`, `27_SECURITY_PRIVACY_AND_COMPLIANCE.md`, `31_FAST_CHANGING_OFFICIAL_REFERENCES.md`, `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`, and the binding corrections in `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`.

Stop only after selective/background research is capability-policy gated, explicitly costed, durable across webhook and polling recovery, evidence-bound, fixture-tested without live egress, and does not create drafts or send outreach.
