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


## 2026-08-05 — Knowledge-base release 2.1 audit

- Current extended research defaults to capability-tested GPT-5.6 reasoning models plus `web_search`; deprecated dedicated deep-research policies are disabled by default.
- Background Mode/ZDR is modeled as a provider capability with `store=false` support and a short reverified retrieval window, not a categorical incompatibility.
- Contact routes now record public versus human origin; public extraction cannot infer warm introductions or existing relationships.
- Outreach is represented as exact-bound content units and rendered deterministically before review/approval.
