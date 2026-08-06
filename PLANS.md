# Implementation Plan

**Selected milestone:** 1 — Accounts, audit, operations, and transactional outbox  
**Visible outcome:** Authenticated, role-aware operators can inspect a dark operational workspace, create a durable checkpoint command, observe its pipeline/audit/outbox records, and safely retry an eligible publication. Database commits survive broker publication failure, stale claims recover, and duplicate delivery cannot duplicate the domain effect.  
**Plan opened:** 2026-08-05  
**Predecessor:** Milestone 0 verified on 2026-08-05

## Relevant specifications

- `AGENTS.md`
- `docs/ftl-opportunity-intelligence/README.md`
- `docs/ftl-opportunity-intelligence/06_DATABASE_SCHEMA_AND_MIGRATIONS.md`
- `docs/ftl-opportunity-intelligence/07_DOMAIN_STATES_AND_AUDIT_TRAIL.md`
- `docs/ftl-opportunity-intelligence/23_DASHBOARD_UX_SPECIFICATION.md`
- `docs/ftl-opportunity-intelligence/24_CELERY_ORCHESTRATION_AND_SCHEDULING.md`
- `docs/ftl-opportunity-intelligence/26_OBSERVABILITY_AND_OPERATIONS.md`
- `docs/ftl-opportunity-intelligence/27_SECURITY_PRIVACY_AND_COMPLIANCE.md`
- `docs/ftl-opportunity-intelligence/28_TESTING_EVALUATION_AND_QUALITY_GATES.md`
- `docs/ftl-opportunity-intelligence/30_CODEX_IMPLEMENTATION_ROADMAP.md`
- `docs/ftl-opportunity-intelligence/32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`

## Repository findings

- Milestone 0 has executed its aggregate Docker verification, persistence check, backup, and isolated restore drill. The development stack is healthy and PostgreSQL contains 39 framework/Beat migrations.
- No project-owned database model currently exists. `apps.operations` is an empty ownership boundary and the root route exposes only health/admin paths.
- The existing database was initialized with Django's built-in `auth.User`. Replacing it after framework migrations would create an unsafe migration dependency transition; milestone 1 will preserve it and add an FTL-owned `TeamRole` relation and seeded Django groups/permissions.
- No broker publication occurs from application transactions. This milestone can introduce the outbox without a compatibility shim or competing legacy path.
- The branch remains `main`; the pre-existing dirty and untracked user files are preserved. No destructive database reset, volume removal, or migration rewrite is authorized.
- `django-csp` 4.0 is the current stable release supporting Django 5.2/Python 3.13 and will provide the application CSP middleware.

## Milestone ownership

### Django models and migrations

- `accounts.TeamRole`: one active FTL role (`admin`, `founder`, `researcher`, `reviewer`, or `viewer`) per Django user, with group-backed permissions and retained historical user identity.
- `operations.PipelineRun` and `PipelineStepRun`: canonical queued/running/completed/failed progress, correlation, heartbeat, safe context, version, and idempotent step effect.
- `operations.TaskOutbox`: unique command key, small JSON payload, explicit claim/publication/retry state, broker message ID, safe error, owner, and timestamps, indexed by eligibility.
- `operations.ProviderCall`: append-oriented provider operation/cost/status shell only; it performs no provider call in this milestone.
- `operations.AuditEvent`: append-only actor/action/object summaries and request/run correlation. PostgreSQL triggers reject update/delete in addition to application guards.
- One fresh-install-compatible migration per new app, plus a conditional PostgreSQL audit immutability trigger. No data deletion or existing migration edit.

### Pydantic contracts and services

- Strict `TaskEnvelopeV2` and checkpoint-command contracts carry UUIDs/scalars only and reject extra/large/untrusted payload state.
- A transactional service creates the pipeline run, audit event, and unique outbox row together; duplicate requests return the same records.
- A bounded dispatcher claims with `select_for_update(skip_locked=True)`, publishes outside the transaction, records broker IDs, applies deterministic backoff, and safely recovers stale claims.
- The idempotent consumer locks the canonical run, creates one unique step effect, transitions it once, and writes one completion audit event. Duplicate delivery becomes a no-op.
- Role assignment and outbox retry use audited transactional services; views never mutate audited statuses directly.

### Celery tasks, queues, and schedules

- `operations.dispatch_outbox` and stale-claim recovery run on `maintenance`; the checkpoint consumer uses late acknowledgment, worker-loss rejection, short limits, ignored results, and the strict envelope.
- `bootstrap_ftl_platform` idempotently seeds the five groups/permissions and database-backed dispatch/recovery schedules. It creates no user or password and keeps all provider policies disabled.
- The only domain-to-broker path is the dispatcher. Celery task arguments contain the envelope of IDs/scalars; PostgreSQL remains canonical and results stay disabled.

### Routes, templates, and static assets

- `/accounts/login/` and logout use Django authentication; all product/operations pages require login and permission checks, with explicit 403 handling.
- `/` provides the restrained dark overview shell with operations health/backlog and recent decisions; `/operations/`, `/operations/runs/`, `/operations/outbox/`, and `/operations/audit/` expose server-filtered durable state.
- POST-only checkpoint creation and eligible outbox retry work without JavaScript, include CSRF, preserve request correlation, and surface success/error messages.
- `/health/dependencies` is authenticated and permissioned; public liveness/readiness remain minimal.
- Tokenized CSS supplies semantic tables, visible focus, 44px targets, contrast, status text/shapes, responsive layout, and reduced-motion support. No raw external HTML is rendered.

### Settings and middleware

- Request-correlation middleware accepts only bounded UUID request IDs, generates one otherwise, returns it in `X-Request-ID`, and supplies structured-log context.
- `django-csp` applies a self-only policy with scripts/objects/frames blocked; standard Django CSRF, clickjacking, secure production cookies, Argon2, and deployment checks remain active.
- Safe structured logs add service/event/correlation fields from an allowlist and never serialize arbitrary payloads or secrets.

## Implementation steps

1. Add the accounts/operations models, constraints, admin views, migrations, contracts, request context, and bootstrap command.
2. Implement transactional command creation, safe outbox claim/publish/failure/recovery, idempotent consumer execution, audited retry, and Celery schedules.
3. Implement authenticated overview/operations pages, forms, filters, dependency health, permission handling, templates, and accessible tokenized styling.
4. Add unit tests for contracts, authorization, CSRF, middleware, services, failure/backoff/recovery, duplicate delivery, audit immutability, bootstrap idempotency, and UI rendering.
5. Add PostgreSQL integration tests for concurrent-safe eligibility, transaction rollback, unique idempotency, broker-failure durability, duplicate effects, and the audit trigger; extend browser-level E2E through login and checkpoint creation.
6. Run and fix the full Docker quality interface, migrate the live non-destructively, bootstrap policy data, verify worker dispatch/recovery and UI state, then repeat backup/isolated restore checks for the expanded schema.
7. Record exact evidence in this file and `IMPLEMENTATION_STATUS.md`; add only the built-in-user and outbox claim design decisions to `DECISIONS.md`.

## Failure, retry, security, migration, and rollback

- A broker exception never rolls back the already-committed domain record; it stores only a stable error code and bounded/redacted message, increments attempts, and advances `available_at` using capped backoff.
- Claim ownership prevents a late dispatcher from overwriting another recovery attempt. Publication-before-database-ack may duplicate a message by design; the unique step idempotency key makes the consumer effect exactly once.
- Unknown command types, invalid envelopes, canceled rows, exhausted retries, and non-retryable states fail visibly without blind publication. Manual retry is role-restricted, state-checked, audited, and never changes the idempotency key.
- Audit records are reference/hash summaries only. Model/application guards and a PostgreSQL trigger make them append-only. Errors, UI, and logs omit secrets, raw payloads, cookies, and provider bodies.
- `TeamRole` does not delete or rewrite `auth.User`; deactivation preserves authorship. Role mutation is transactional and group synchronized.
- Migrations are additive and reversible: dropping new tables/trigger is technically possible only through an explicit migration rollback. Normal rollback uses the previous application image while leaving additive tables intact; no automated destructive rollback runs.
- Provider calls and external outreach remain disabled. No legal conclusion, contact route, suppression exception, provider credential, or live model behavior is introduced.
- Backup/restore validation follows the schema migration; the existing backup remains untouched.

## Validation commands and stopping condition

Run inside Docker through the Make interface unless the command validates Compose itself:

```text
make format
make lint
make typecheck
make check-migrations
make check-deploy
make test
make test-integration
make test-e2e
make compose-config
make check-docs
make secret-scan
make verify
make migrate
make bootstrap-data
make up
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
make backup
make restore-drill FILE=<new backup>
```

Stop at a clean verified milestone 1 checkpoint only when the full Docker quality suite passes and executed tests prove: role-aware authentication/403/CSRF; atomic run/audit/outbox creation and rollback; durable broker failure plus later publication; safe stale recovery; duplicate delivery with one step/audit effect; append-only PostgreSQL audit enforcement; idempotent bootstrap/schedules; operations UI visibility of status, attempts, error, owner, correlation, and timestamps; fresh migrations and non-destructive upgrade; healthy live stack; expanded backup integrity and isolated restore. Live OpenAI/provider calls remain intentionally disabled.

## Milestone 1 results

Milestone 1 reached its verified stopping condition on 2026-08-05.

- Added Django `TeamRole`, five group-backed role policies, audited role assignment, and idempotent policy/schedule bootstrap without creating an operator or credential.
- Added `PipelineRun`, `PipelineStepRun`, `TaskOutbox`, `ProviderCall`, and append-only `AuditEvent`; migrations `accounts.0001`, `operations.0001`, and `operations.0002` upgraded the live PostgreSQL database non-destructively from 39 to 42 migration records.
- Added strict Pydantic v2 checkpoint/envelope contracts, atomic service writes, bounded concurrent-safe claims, publish-after-lock-release, safe retry/backoff, stale recovery, audited manual retry, and an idempotent late-acknowledged Celery consumer.
- Added authenticated and permissioned overview/run/outbox/audit/dependency pages, CSRF-only state changes, request correlation, CSP, WhiteNoise static delivery, and a responsive accessible dark workspace.
- Corrected two issues found only in live verification: all Compose application services now share the same locally built immutable image; Celery exchanges use versioned `ftl.v1.*` names so obsolete non-destructively retained Redis bindings cannot multiply delivery. ADR-004 records the queue policy.
- `make format`, `make lint`, `make typecheck`, `make check-migrations`, `make check-deploy`, `make test`, `make test-integration`, `make test-e2e`, and `make compose-config` each exited 0. Results were 88 Ruff-formatted files, no lint issues, no mypy issues in 57 source files, no migration drift, no deployment findings, 61 passing unit tests at 89.68% branch coverage, 4 passing PostgreSQL integration tests, and 2 passing HTTP E2E tests.
- `make check-docs` passed with every local Markdown link resolved. The first secret scan correctly flagged a password-shaped E2E fixture; the fixture now generates a per-test credential, and the final `make secret-scan` passed with no findings.
- Final aggregate `make verify` exited 0 after executing lint, type checking, migration/deployment checks, all three test suites, Compose policy, documentation links, and secret scanning.
- Browser QA verified styled authenticated desktop/mobile flows, no overflow at 390 px, visible keyboard focus, no console warnings/errors, and a UI-created checkpoint progressing to complete/published. The fixture user was deactivated and its password made unusable afterward.
- A final live system checkpoint (`219e7d5e-12d0-4f31-ace9-07f9927dfbde`) completed with one outbox attempt, one broker receipt, one step, and one completion audit. Liveness, readiness (including storage), and CSS delivery returned HTTP 200.
- After aggregate verification and its service recreation, `make up` completed with no pending migrations; both workers answered `pong`, PostgreSQL/Redis/web were healthy, Beat and Caddy were running, and the application remained available at `http://127.0.0.1:8000`.
- `make persistence-check` retained 42 migration records. `make backup` produced `backups/20260805T155046Z/` with a 75,878-byte database dump and valid checksums; its isolated PostgreSQL 18 restore drill passed with all 42 migrations.
- No live provider call was performed. OpenAI, external fetching, contact/email features, and first-contact sending remain disabled.

The next milestone is 2 — Companies, sources, artifacts, and safe manual ingestion — governed by specifications `06`, `09`, `10`, `23`, and `27`.

## Milestone 0 verified checkpoint

Milestone 0 reached its verified stopping condition on 2026-08-05.

- `make bootstrap`: created `.env` once with generated local secrets at mode `0600`; built the Python 3.13.14 runtime and quality images from the locked dependency graph.
- `make format`: Ruff formatted the implementation and applied safe import/lint fixes.
- `make lint`: 51 Python files formatted; Ruff reported `All checks passed!`.
- `make typecheck`: strict mypy with the Django plugin reported `Success: no issues found in 27 source files`.
- `make check-migrations`: reported `No changes detected`.
- `make check-deploy`: Django 5.2 production deployment checks reported no issues under CI-safe HTTPS settings.
- `make test`: 24 unit tests passed; branch coverage was 86.09% against the enforced 80% floor. Live-provider tests were excluded by marker.
- `make test-integration`: one PostgreSQL integration test passed against PostgreSQL 18.4 and confirmed all migrations applied.
- `make test-e2e`: one real HTTP live-server health flow passed.
- `make compose-config`: base, development, and production Compose rendered successfully; policy checks confirmed the PostgreSQL 18 parent volume, private base/production data services, loopback-only development ports, prebuilt production application image, read-only application roots, and no source binds/migration commands in production processes.
- `make check-docs`: all local Markdown links resolved.
- `make secret-scan`: no potential secrets were found in implementation files; ignored local `.env`, generated backups, the lock file, caches, Git internals, and the normative knowledge-base package are excluded deliberately.
- Final aggregate `make verify`: exit `0` after running all checks above.
- `make up`: explicit one-shot migration service applied 39 Django/Beat migrations, then web, PostgreSQL, Redis, two Celery workers, database-backed Beat, and Caddy reached running/healthy state.
- Runtime probes: `/health/live` returned `{"status":"live"}`; `/health/ready` returned ready with configuration/database/migrations all `true`.
- Runtime identity/version checks: web and worker ran as UID/GID `10001`; Python `3.13.14`, PostgreSQL `18.4`, Redis `8.8.1`, Celery `5.6.3`, and Django `5.2.17` were observed in their containers.
- Worker logs confirmed distinct direct exchange/routing-key bindings, Redis broker connection, disabled Celery results, core concurrency 2, research concurrency 1, and database-backed Beat startup.
- `make persistence-check`: the named PostgreSQL volume retained all 39 migration records across a stop/recreate cycle.
- `make backup`: produced a 47,730-byte custom-format database dump, a media archive, JSON manifest, and verified SHA-256 checksums under ignored `backups/20260805T150009Z/`.
- `make restore-drill FILE=backups/20260805T150009Z/database.dump`: restored into an isolated temporary PostgreSQL 18 container and verified all 39 migration records without touching the canonical database.
- No live OpenAI/provider call was made. All provider feature flags remain disabled.

The next plan is milestone 1 — Accounts, audit, operations, and the durable transactional outbox — using specifications `06`, `07`, `23`, `24`, `26`, and `27`. Its stopping condition is a permissioned operational dashboard where a service transaction writes a domain record and outbox row, a simulated broker outage leaves the row durable, recovery publishes it idempotently, and the operations UI exposes attempts/state.
