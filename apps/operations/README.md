# Operations application ownership

`apps.operations` owns durable pipeline/provider-call records, append-only audit events, the transactional outbox, Celery dispatcher/recovery tasks, and permissioned operations views. Milestone 1 implements the checkpoint vertical slice with strict Pydantic envelopes, PostgreSQL-canonical state, bounded `SKIP LOCKED` claims, retry/backoff, stale-claim recovery, and idempotent consumer effects. Provider records are a durable shell only; no live provider integration exists yet.
