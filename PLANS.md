# Implementation Plan

**Selected milestone:** Milestone 5 production refinement — DACH creative-AI and learning discovery recall
**Visible outcome:** Daily and manual discovery use a separate, measurable German/English creative-learning search family that can find HOFFMANN-EITLE-like public roles by task language, safely fetch and monitor them, and classify exact German creative/learning evidence without hardcoding a company.
**Plan opened:** 2026-08-07
**Predecessor:** Milestone 11 remains verified; this is a bounded correction to the already-deployed milestone-5 policy.

## Active refinement plan

- Specifications: `08_SEARCH_DEFINITIONS_AND_DISCOVERY.md`, `11_SIGNAL_DETECTION_AGENT.md`, `24_CELERY_ORCHESTRATION_AND_SCHEDULING.md`, `25_OPENAI_CLIENT_MODEL_ROUTING_AND_COSTS.md`, `28_TESTING_EVALUATION_AND_QUALITY_GATES.md`, `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`, and binding audit corrections in `32`.
- Finding: production had one English operations-focused definition. Its only live query did not contain creative-video, learning-content, German part-time, or Munich vocabulary, despite the normative specification requiring that query family.
- Owned change: a second immutable `SearchDefinition`, discovery prompt/policy v2.1.0, German/English role/task query rendering, automatic watches for registered discovery endpoints, and signal ontology/detector v1.1.0 with exact German creative-learning phrases.
- Failure/security: candidates remain non-evidence until isolated safe fetch and deterministic parse; excluded domains, budgets, strict provider source references, SSRF checks, immutable artifacts, and replay-safe outbox behavior remain unchanged. Separate query families make cost/yield measurable; two scheduled definitions reserve at most USD 1.00/day before later policy tuning.
- Data/rollback: no schema migration. Bootstrap appends/activates immutable policy records and watches existing active endpoints. Rollback deactivates the creative-learning definition without deleting candidates, artifacts, jobs, signals, or audit history.
- Validation: focused Docker tests, full `make verify`, bootstrap idempotency, production Compose deployment, one bounded live manual discovery, downstream source/job/signal inspection, and healthy worker/readiness checks.
- Stopping condition: the live definition is active, HOFFMANN-EITLE-like terms are present without a company name, a bounded live run is observable, registered endpoints are watched, and all Docker gates pass.

No new ADR is required: this implements the already-specified creative/learning query family and milestone-5 acceptance behavior.

## Locally verified refinement checkpoint

- Discovery prompt/policy v2.1.0 and signal detector/ontology v1.1.0 are implemented. The neutral German fixture produces both `creative_ai_production` and `learning_content`, and the search fixture proves the required vocabulary is rendered without naming a target employer.
- Focused Docker verification passed 28 discovery/provider/signal/auth/integration/E2E tests.
- Final aggregate `make verify` exited 0: 295 files were formatted/Ruff clean; strict mypy passed across 220 source files; migration drift and production deployment checks passed; 161 unit tests passed at 80.10% coverage; 14 PostgreSQL integration tests and 10 real-HTTP E2E tests passed; Compose, document-link, and secret gates were clean.
- No schema migration is required. Production deployment, idempotent bootstrap, one bounded live provider run, and downstream endpoint/job/signal inspection remain before the refinement stopping condition is met.

## Prior milestone 11 plan and checkpoint

**Selected milestone:** 11 — Buyer roles and public/human contact routes  
**Visible outcome:** An approved current solution and completed asset match can produce evidence-bound buyer-role categories, scan only registered official public sources through the SSRF-safe fetcher for explicitly published contact routes, preserve encrypted route values and exact provenance, and require separate human eligibility/legal review and exact target selection. Buyer roles, people, observations, routes, deliverability, suppression, and recommendation remain independent. Email drafting and sending remain out of scope.  
**Plan opened:** 2026-08-06  
**Predecessor:** Milestone 10 verified on 2026-08-06

## Relevant specifications

- `docs/ftl-opportunity-intelligence/16_CONTACT_DISCOVERY_AND_VERIFICATION.md`
- `docs/ftl-opportunity-intelligence/18_SOLUTION_DESIGN_AGENT.md`
- `docs/ftl-opportunity-intelligence/23_DASHBOARD_UX_SPECIFICATION.md`
- `docs/ftl-opportunity-intelligence/27_SECURITY_PRIVACY_AND_COMPLIANCE.md`
- `docs/ftl-opportunity-intelligence/24_CELERY_ORCHESTRATION_AND_SCHEDULING.md`
- `docs/ftl-opportunity-intelligence/28_TESTING_EVALUATION_AND_QUALITY_GATES.md`
- `docs/ftl-opportunity-intelligence/33_AGENT_PROMPT_ENGINEERING_STANDARD.md`
- binding corrections in `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`

## Repository findings

- Milestone 10 is verified by the complete Docker gate: 152 unit tests at 80.59% coverage, 13 PostgreSQL integration tests, 9 real-HTTP E2E tests, clean Ruff/mypy/migrations/deployment/Compose/docs/secrets. Versioned knowledge, solution hypotheses, and zero-to-two safe asset matching are durable and email remains absent.
- The current live opportunity is research eligible, not solution-approved, because live OpenAI calls were not authorized. Deterministic fixtures can exercise the entire milestone-11 precondition chain without provider egress.
- Contact-route encryption/HMAC environment names already exist, but runtime loading, key validation, cryptography, contact models/services/tasks/routes, buyer-role inference, public route scanning, human route provenance, suppression, review, and selection do not exist.
- Standard research intentionally excludes named contacts/final buyers. Milestone 11 must derive role categories only from the approved solution and may scan only exact registered official sources; it may return no person and no route rather than guess.

## Owned implementation

- Add a `contacts` app owning immutable buyer-role results/hypotheses, public fetch artifacts/evidence, person role observations, and selection history plus independently mutable route state and append-only suppression entries.
- Add strict Pydantic v2 `BuyerRoleResultV2` and `ContactRouteResultV2` contracts. Deterministically infer role categories from the exact approved solution requirements and validated evidence IDs; never emit people, addresses, reporting lines, or routes from role inference.
- Add bounded ID-only `contacts.infer_roles` and per-source `contacts.scan_source` continuations on `contact_enrichment`. Select only current research sources classified official-company and matching a verified/observed company domain; fetch via the existing pinned SSRF-safe adapter, store immutable artifacts/hashes, and never render raw HTML.
- Extract only literal `mailto:`, `tel:`, form actions, contact links, and allowed professional-profile URLs with exact source/evidence spans. Encrypt email/phone/human values with an AEAD key, deduplicate/suppress via a separate keyed HMAC, and fail closed when keys are unavailable.
- Add explicit human-origin route creation with actor/provenance, route eligibility/legal review, suppression checks, and exact solution/buyer-role/route selection. Public extraction can only create `public_source` routes with deliverability `unknown` and eligibility `unreviewed`.
- Add authenticated contact workspaces to company/opportunity pages with provenance, origin, freshness, observation, deliverability, eligibility, legal status, row version, and audit visibility; do not create packets, drafts, or sends.

## Implementation steps

1. Add contact crypto/runtime settings, strict contracts, models, permissions/admin, additive migrations, constraints, and PostgreSQL immutability triggers.
2. Implement approved-solution-bound role inference and transactional outbox continuation to one command per eligible registered official source.
3. Implement bounded safe fetch, immutable storage artifact/evidence registration, literal route extraction, normalization/encryption/HMAC deduplication, terminal/failure handling, and replay safety.
4. Implement authorized human routes, independent route review/legal status, synchronous suppression, and exact human target selection with audit history.
5. Build company/opportunity contact pages and test role-only/no-route, literal form/mailto, guessed-address rejection, hostile HTML, human-origin restrictions, crypto-at-rest, duplicate HMAC, stale/independent states, suppression, PostgreSQL triggers, and real-HTTP flow.

## Failure, retry, security, migration, and rollback

- Route scans use registered source IDs only, revalidate DNS and every redirect, pin approved addresses, bound content/time/bytes, persist hashes/artifacts, and never display raw HTML. Source failure is explicit and cannot create a route.
- Sensitive values never enter Celery payloads/logs/errors and are encrypted before database persistence. Separate keys and key IDs support future rotation; missing/invalid keys block route creation safely.
- Role and scan commands are idempotent/retry-safe. Every extracted route retains exact evidence; repeat observations update bounded freshness state without duplicating immutable evidence/history.
- Suppression is synchronous before eligibility and selection. Public extraction cannot approve, verify deliverability, or create warm/existing/event routes. Only permissioned human services may review/select.
- Migrations are additive. Rollback disables new routes/tasks while retaining encrypted routes and immutable evidence/history. No live model call, packet, email generation, or sending is part of this milestone.

## Validation and stopping condition

Run `make format`, `make lint`, `make typecheck`, migration/deploy checks, unit/integration/E2E suites, Compose/docs/secret gates, and final `make verify` inside Docker. Apply migrations once through the release service, rebuild/restart the shared image, execute deterministic approved-solution and safe-fetch fixtures without provider/model egress, verify workers/health, and inspect the workspace.

Stop only when role-only inference is exact-solution/evidence-bound; public route extraction can persist only literal source-backed routes; human-origin routes require actor/provenance; encrypted value, HMAC, observation, freshness, deliverability, eligibility, legal review, recommendation, and suppression remain independent; exact human selection is required; email remains absent; the application is runnable; and every Docker gate passes.

## Verified Milestone 11 checkpoint

- Added strict buyer-role/contact contracts and a dedicated contact domain. An approved exact solution with a completed asset match queues deterministic, evidence-bound role hypotheses, then one short `contacts.scan_source` command per eligible registered official-company source. Role inference never emits a person or route, and a complete zero-route result is valid.
- Official-source scans reuse the controlled-DNS, address-pinned, redirect-revalidating SSRF-safe fetcher. Parsing removes inactive/executable markup and accepts only literal `mailto:`, `tel:`, form-action, and contact-link observations. It cannot infer a likely address, a warm introduction, or an existing relationship.
- Raw contact source bodies, sensitive exact evidence fragments, and email/phone/human route values are AES-256-GCM encrypted before storage. A separate keyed HMAC supports deduplication and synchronous suppression without exposing the route; key IDs, masked displays, hashes, retrieval times, offsets, and immutable artifact/evidence provenance remain durable.
- Added separately reviewed route origin, observation, freshness, deliverability, outreach eligibility, legal status, recommendation, suppression, and exact opportunity selection state. Human-origin routes require an authorized actor and provenance. Selection requires an eligible, legally approved, unsuppressed route and creates no packet, draft, email, or send.
- Additive `contacts` migrations 0001–0002 were applied once through the rebuilt release image. PostgreSQL triggers reject buyer-role/evidence mutation or deletion. The shared web, worker, Beat, and proxy services restarted healthy with the new image.
- Final aggregate `make verify` exited 0: 294 files were formatted/Ruff clean; strict mypy passed across 220 source files; migration drift and production deployment checks passed; 158 unit tests passed at 80.06% coverage; 14 PostgreSQL integration tests and 10 real-HTTP E2E tests passed; Compose, document-link, and secret gates were clean. No live provider call or live contact-source scan was performed; deterministic fixtures exercised the complete safe-fetch path.

## Verified Milestone 10 checkpoint

- Added strict editorial contracts and an append-only knowledge release registry for offers, approved/prohibited claims, and assets. Sync and activation are separate operations; activation records the actor, reason, prior release, current release, and invalidates dependent current solutions without deleting history.
- Added immutable solution versions, phases, exact research/knowledge/input hashes, editable version replacement, exact approval binding, and a downstream asset-match record. Python validates every evidence/claim/offer reference and applies public-status, external-approval, confidentiality, audience, language, review-freshness, and URL-health filters before selecting at most two assets.
- The checked-in starter release contains one reviewed offer module and intentionally empty claim/asset catalogs. Empty catalogs and a valid zero-asset match are first-class outcomes; the implementation invents no FTL proof or downloadable asset.
- Added ID-only `solutions.design` and `solutions.match_assets` outbox commands on dedicated queues, durable run/step/audit state, replay-safe domain effects, and authenticated release, asset, solution, and opportunity workspaces. No draft or email record is created.
- Additive migrations `knowledge` 0001–0002 and `solutions` 0001–0002 were applied once through the rebuilt release image. PostgreSQL triggers reject mutation/deletion of immutable knowledge and solution records.
- Docker checkpoint results before the final aggregate gate: focused M10 tests 5 unit, 1 PostgreSQL, and 1 real-HTTP test passed; full `make test` 151 passed at 80.18% coverage; `make test-integration` 13 passed; `make test-e2e` 9 passed. No live provider call was made.

## Verified Milestone 9 checkpoint

- Docker checkpoint commands passed: migration drift clean; `make test` 146 passed at 81.14% coverage; `make test-integration` 12 PostgreSQL tests passed; `make test-e2e` 8 real-HTTP tests passed.
- Additive migrations `opportunities` 0003 and `research` 0001–0002 are applied once through the rebuilt release image. PostgreSQL rejects mutation/deletion of registered reports, sources, claims, claim links, evidence links, and dossiers.
- The central adapter uses `responses.create` for the cited web report and a separate `responses.parse` Structured Output call with no tools for extraction. Immutable active policies own model/tool/reasoning/budget/retention configuration.
- A research request atomically records brief/public input hashes, pipeline/outbox/audit state, then registers provider-derived `SRC-` IDs before accepting `CLM-` claims bound only to supplied sources, signals, and evidence. Python renders and hashes the canonical dossier.
- Disabled-provider, fabricated-source, partial-report preservation, duplicate delivery, private-context isolation, source integrity, PostgreSQL immutability, permissions, and real-HTTP research pages are verified with deterministic fixtures. No live OpenAI call was made.

## Verified Milestones 7–8 checkpoint

- Docker checkpoint commands passed: no migration drift; 142 unit tests at 81.50% coverage, 11 PostgreSQL integration tests, and 7 real-HTTP E2E tests.
- Five live Hostinger signals completed deterministic `CapabilityAssessmentV2` classification with exact assessment-evidence links, one mutually exclusive mode, Python-owned relevance scores, 0.800 coverage, and explicit asset/strategic unknowns. PostgreSQL rejects assessment-evidence-link mutation.
- Five time-bounded company assessments were appended through concurrent aggregation commands; four were superseded without deletion. The current assessment selects all five signals and records every required feature, cutoff/input hash, four supported company patterns, priority 71, and overall coverage 0.670.
- One active Hostinger capability-systems opportunity is research eligible with independent research/solution/outreach/relationship states. Qualification and mode overrides are actor/reason audit records, not rewrites, and survive automatic rescoring.
- Browser QA verified the ranked workspace and opportunity detail with score decomposition, missing fields, feature snapshot, source-linked signals, policy versions, status, and next action. No OpenAI call was made.

## Verified Milestone 6 checkpoint

- Final `make verify`: exit 0; 205 files formatted/Ruff clean, strict mypy clean across 149 source files, no migration drift or deployment issues, 138 unit tests at 82.36% coverage, 10 PostgreSQL integration tests, 6 real-HTTP E2E tests, and clean Compose/docs/secret gates.
- Five additive migrations create exact evidence catalogs/items, signal ontology/attempt/event/evidence state, PostgreSQL immutability triggers, and explicit detector-policy supersession review state. All are applied through the release service.
- Live public Hostinger Ashby ingestion produced 72 canonical jobs/events. Current deterministic detector/ontology 1.0.2 produced 72 immutable catalogs, 553 items, 67 explicit no-signal outcomes, and 5 active signals without an OpenAI call.
- Exact phrase boundaries replaced unsafe substring matching after browser QA exposed `etl` inside `quietly`. Two earlier smoke detector versions remain durable; 15 prior results are retracted as superseded with system audits, not deleted.
- The active Signal Inbox and detail page expose exact quotes, offsets, hashes, source artifact, posting/company/run links, freshness, confidence, and all detector/prompt/schema/ontology versions. Reviewer retraction is permissioned, reasoned, audited, and non-destructive.
- Strict `SignalDetectionResultV2` matches the canonical required-key contract. Invalid IDs/tags/event kinds/snapshots, commercial rationale, prompt-injection-like text, generic AI, and replay cannot create duplicate or unsupported observations.

## Verified Milestone 5 checkpoint

- Four additive migrations introduced immutable search/model policy, discovery run/query/candidate/watch state, provider bounds, and durable leases. The live release migration and idempotent bootstrap completed without data loss.
- Final `make verify`: exit 0; 182 files formatted/Ruff clean, strict mypy clean across 131 source files, no migration drift or deployment issues, 126 unit tests at 83.37% coverage, 8 PostgreSQL integration tests, 5 real-HTTP E2E tests, and clean Compose/docs/secret gates.
- Live manual run `a3a260d0-6249-45db-bbf0-950efdf8bec7` completed and published through the outbox, then queued three watched endpoints through the ordinary source pipeline. The provider path stayed explicitly disabled; no live OpenAI call occurred.
- Real downstream outcomes were safe and visible: Ashby HTTP 304 complete with no duplicate jobs, example.com complete, and the oversized legacy OpenAI board failed `FETCH_RESPONSE_TOO_LARGE` without domain effects.
- Browser QA verified definition/run/candidate navigation, schedule/window/budget metrics, warning and pipeline visibility, semantic tables, and explicit diagnostic-not-evidence labeling.
- ADR-008 records the typed adapter, immutable provider policy, conservative budget reservations, and PostgreSQL lease choice. README and `.env.example` document actual startup/manual discovery and opt-in provider requirements.

## Verified Milestone 4 checkpoint

- Final `make verify`: exit 0; 118 unit tests at 83.79% coverage, 7 PostgreSQL integration tests, 4 E2E tests, plus formatting/Ruff, mypy (106 source files), migration/deploy, Compose, docs, and secret gates.
- Live Ashby conditional re-poll: HTTP 304; one new fetch attempt, 56 observations, and 56 cosmetic normalizer-upgrade events. PostgreSQL retained 56 postings and 112 immutable normalized snapshots.
- Browser QA showed the source-backed posting, last-seen update, absence counter, exact versioned change timeline/diff, duplicate section, and immutable snapshot history.
- Five additive jobs migrations are applied; PostgreSQL triggers reject normalized-snapshot and posting-change-event mutation.
