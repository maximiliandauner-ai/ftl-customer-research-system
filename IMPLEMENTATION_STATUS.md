# Implementation Status

**Status:** Milestone 1 verified; application runnable  
**Knowledge-base release:** 2.1 (audited)  
**Completed milestone:** 1 — Accounts, audit, operations, and transactional outbox  
**Next milestone:** 2 — Companies, sources, artifacts, and safe manual ingestion  
**Last updated:** 2026-08-05

## Verified software

- Milestone 0's pinned Python 3.13.14/Django 5.2.17/PostgreSQL 18.4/Celery 5.6.3/Redis 8.8.1 foundation, private base data services, explicit release migration, typed configuration, health checks, and backup/restore controls remain intact.
- Django authentication plus one canonical `TeamRole` per retained user; five idempotently seeded role groups and permission policies; audited transactional role assignment.
- `PipelineRun`, unique `PipelineStepRun`, `TaskOutbox`, `ProviderCall`, and append-only `AuditEvent` models with additive migrations, constraints, operational indexes, and PostgreSQL update/delete rejection for audits.
- Strict Pydantic v2 checkpoint/envelope contracts carrying IDs and bounded scalars only; atomic run/audit/outbox creation; bounded PostgreSQL `SKIP LOCKED` claims; publish outside row locks; safe errors, retry/backoff, stale-claim recovery, manual audited retry, and exactly-once domain effects under duplicate task delivery.
- JSON-only Celery messages, disabled result backend, late acknowledgements, explicit queue policy, versioned direct exchanges, a ten-second outbox dispatcher, and a sixty-second stale-claim recovery schedule.
- Authenticated overview, pipeline run, outbox, audit, retry, and detailed dependency-health pages with explicit permissions, CSRF-protected POST actions, request correlation, safe status detail, and no raw fetched/provider content.
- Restrained dark responsive UI with semantic structure, visible focus, status text/shapes, reduced-motion handling, and immutable WhiteNoise static assets included in the shared runtime image.
- CSP, clickjacking, CSRF, secure production cookies, Argon2, allowlisted structured logging, redaction, writable-storage readiness, and provider/outreach feature gates remain fail-closed.

## Executed checkpoint evidence

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

No OpenAI or other live provider calls were performed. OpenAI, web search, deep research, contact research, email integration, reply ingestion, Playwright fetching, and first-contact sending remain disabled. `ProviderCall` is storage/operations scaffolding only and no adapter exists yet.

## Open work and risks

- Milestone 1's only domain command is the integrity checkpoint. Companies, source provenance, immutable artifacts, safe outbound fetching, normalized postings, signals, scoring, research, contacts, and outreach remain later milestone work and have no placeholder production paths.
- Old disposable Redis binding keys from the pre-milestone-1 queue topology remain in the local named volume because destructive cleanup was prohibited. Versioned `ftl.v1.*` exchanges isolate them; a fresh command was observed exactly once after restart. ADR-004 records the migration policy.
- Local development backups are unencrypted. Production rollout must enable encrypted backup storage and complete the server restore rehearsal in milestone 15.
- No active test or production operator account, production domain, credential, or TLS certificate was left behind. An administrator must create the first real operator explicitly.

## Next verified stopping condition

Complete milestone 2 using `06_DATABASE_SCHEMA_AND_MIGRATIONS.md`, `09_SOURCE_CONNECTORS_AND_FETCHING.md`, `10_NORMALIZATION_DEDUPLICATION_AND_CHANGE_DETECTION.md`, `23_DASHBOARD_UX_SPECIFICATION.md`, and `27_SECURITY_PRIVACY_AND_COMPLIANCE.md`.

Stop only after an authorized user can submit a public URL; every hop passes DNS/IP/redirect/size/content-type/time-limit validation; a safe fetch creates inspectable company/source/candidate/observation/immutable artifact metadata with retrieval time, hash, parser version, and storage reference; no raw fetched HTML is rendered; unsafe destinations are blocked; and deterministic unit/PostgreSQL/E2E tests plus the full Docker quality suite pass.
