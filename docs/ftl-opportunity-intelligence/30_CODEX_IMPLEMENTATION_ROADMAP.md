# 30 — Codex Implementation Roadmap

**Specification version:** 2.1  
**Primary owner:** Engineering leadership

## Purpose

Provide dependency-aware vertical milestones that keep the application runnable, testable, and reviewable. Codex must implement the first incomplete milestone, not create one giant repository-wide diff.

## Milestone rules

Each milestone includes:

```text
objective
relevant knowledge-base files
models/schemas/services owned
visible behavior
migration impact
tests and security cases
operations visibility
documentation/configuration changes
explicit out-of-scope items
definition of done
```

At the end of every milestone, update `IMPLEMENTATION_STATUS.md` and `DECISIONS.md`, run Docker-based quality commands, and leave the application usable.

## Milestone 0 — Audited repository foundation

Read: `02`, `03`, `04`, `05`, `24`, `27`, `28`, `29`, `32`.

Implement:

- Python 3.13/Django 5.2 LTS project;
- exact dependency lock;
- multi-stage non-root Docker image;
- secure base/dev/prod Compose files;
- PostgreSQL 18 correct volume path;
- broker, Celery, Beat, outbox dispatcher shell;
- settings/secrets including `_FILE` support;
- health endpoints;
- Make targets;
- test/lint/typecheck baseline;
- root `AGENTS.md`, status, decisions.

Definition of done: clean clone + env starts; database persists; production checks pass with CI-safe config; tests run in Docker; backup/restore skeleton exists.

## Milestone 1 — Accounts, audit, operations, outbox

Read: `06`, `07`, `23`, `24`, `26`, `27`.

Implement users/roles, audit event, pipeline/provider-call shell, task outbox and dispatcher, dashboard shell, operations pages, request correlation, secure permissions.

Definition of done: a test service writes a domain record and outbox row; broker outage/recovery publishes later; operations displays it.

## Milestone 2 — Companies, sources, artifacts, safe manual ingestion

Read: `06`, `09`, `10`, `23`, `27`.

Implement Company/Domain/Alias, SourceEndpoint/Candidate/FetchObservation/SourceArtifact, safe URL submission/fetch, storage abstraction, SSRF tests, company/source pages.

Definition of done: user submits a public URL, safe fetch/artifact/provenance are inspectable; unsafe URL blocked.

## Milestone 3 — Deterministic connectors and canonical postings

Read: `08`, `09`, `10`, `31`.

Implement Personio, Greenhouse, JSON-LD first; then Lever/Ashby/generic HTML. Add normalized posting/location, snapshots, connector fixtures, lifecycle.

Definition of done: fixtures and at least one manual public source create canonical posting/snapshot without FTL interpretation.

## Milestone 4 — Change detection and deduplication

Read: `10`, `06`, `07`, `28`.

Implement hashes, material/cosmetic/closure/reopen, duplicate relationships, source timeline/diff, outbox eligibility, concurrency constraints.

Definition of done: repeated/translated sources do not duplicate domain effects; material updates are visible.

## Milestone 5 — Search definitions and scheduled discovery

Read: `08`, `24`, `25`, `26`.

Implement query registry, OpenAI web-search adapter, candidate/source registration, watched endpoints, daily Beat schedule, budgets, run metrics, provider error visibility.

Definition of done: scheduled/manual search produces safe candidates; known endpoints are polled directly on subsequent runs.

## Milestone 6 — Observed signals and evidence extraction

Read: `11`, `25`, `27`, `28`, `33`.

Implement deterministic event rules, optional Structured Output evidence extractor, quote validation, signal/evidence models, prompt registry/evals, signal inbox evidence view.

Definition of done: HOFFMANN-EITLE-like fixture creates one exact-evidence signal; injection/unrelated fixture does not.

## Milestone 7 — Capability gaps and deterministic scoring

Read: `12`, `13`, `06`, `28`, `33`.

Implement ontology, classifier, mutually exclusive opportunity mode, component judgments, Python scoring, review filters/actions, evaluation report.

**First operational release.**

Definition of done: founders can discover/inspect/qualify explainable signals locally; backup/restore works.

## Milestone 8 — Company patterns and aggregation

Read: `13`, `07`, `23`.

Implement CompanyPattern, temporal features, momentum, company assessment, opportunity candidate, company ranking. Do not store cluster inference as SignalEvent.

## Milestone 9 — Standard two-pass company research

Read: `14`, `25`, `26`, `27`, `33`.

Implement research brief, web-search report, provider citations/all sources, source registry, no-web extraction, claims, Markdown rendering, freshness, workspace.

Definition of done: every factual claim opens a real provider-derived source; no private FTL context entered public call.

## Milestone 10 — FTL knowledge, solution design, and asset matching

Read: `17`, `18`, `23`, `33`.

Implement knowledge sync/releases, offer/assets/claims, confidentiality filtering, solution prompt, phased editor/version approval, downstream zero-to-two asset matching (including a valid zero-asset result), and invalidation.

## Milestone 11 — Buyer roles and contact routes

Read: `16`, `18`, `27`, `23`.

Implement buyer-role inference after solution, public route research/extraction, contact observation/route, freshness, suppression/legal status, human target selection.

## Milestone 12 — Packet, drafting, factual review, approval

Read: `19`, `20`, `21`, `23`, `27`, `33`.

Implement canonical packet hash, structured subject/body/short-message units with exact bindings, deterministic rendering/review, optional AI critic, exact-version approval, no auto-send, and optional external provider draft behind a disabled flag.

## Milestone 13 — Selective deep research

Read: `15`, `24`, `25`, `26`, `27`.

Implement authorization, background start, response ID, verified webhook, polling fallback, retrieval-window handling, source extraction, budgets/concurrency. Add only after standard research works.

## Milestone 14 — Interactions, replies, follow-up, analytics

Read: `22`, `23`, `26`, `28`.

Implement immutable interactions, email adapter boundary, untrusted reply classifier, immediate suppression, human stage transitions, follow-ups, outcome analytics and evaluation feedback.

## Milestone 15 — Server release rehearsal

Read: `04`, `05`, `26`, `27`, `29`.

Implement/verify production Compose, Caddy/TLS profile, secrets, server webhook, backups, clean restore, deployment runbook, security checks, and laptop-to-server rehearsal.

## Final acceptance scenario

1. Start on a clean laptop using Docker.
2. Discover or submit a HOFFMANN-EITLE-like posting.
3. Inspect source artifact, normalized posting, snapshots, exact evidence, and scoring.
4. Aggregate related company signals.
5. Run cited public research.
6. Approve an FTL Create–Build–Enable solution and a current asset-match result.
7. Select a sourced public or explicit human-origin route;
8. build a deterministic packet;
9. generate an unsent structured-unit draft with exact bindings and deterministic rendering;
10. review each claim/source and approve exact version;
11. record interaction/reply/suppression;
12. back up and restore the complete state into a clean server-like stack.
