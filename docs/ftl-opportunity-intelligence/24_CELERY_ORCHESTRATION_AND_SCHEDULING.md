# 24 — Celery Orchestration, Transactional Outbox, and Scheduling

**Specification version:** 2.1  
**Primary owner:** Task orchestration

## Purpose

Define reliable database-to-broker dispatch, queues, task contracts, retries, idempotency, schedules, time limits, recovery, and cancellation for Celery 5.6.

## Core decisions

- PostgreSQL domain records and `PipelineRun` are canonical.
- Use a transactional `TaskOutbox`; `transaction.on_commit()` alone is not sufficient for reliable publication.
- Celery task arguments contain IDs/scalars only.
- Tasks normally set `ignore_result=True`; do not use `django-celery-results` as a second business-state store.
- Long provider jobs use start/poll tasks, not worker-blocking loops.
- Redis is acceptable for local/single-server transport; RabbitMQ MAY be introduced later through an ADR if measured delivery/scale needs justify it.

## Queues

```text
discovery
fetch
parse
classification
aggregation
research
deep_research
solution_design
asset_matching
contact_enrichment
drafting
review
maintenance
```

Suggested workers:

```text
worker-fast: all short/medium queues except research/deep_research
worker-research: research and deep_research start/poll/extract tasks
optional worker-browser: Playwright queue
```

## TaskEnvelopeV2

```json
{
  "schema_version": "2.1",
  "outbox_id": "uuid",
  "pipeline_run_id": "uuid",
  "command_type": "signals.classify",
  "object_id": "uuid",
  "idempotency_key": "...",
  "requested_by": "user_uuid|system",
  "policy_version": "2.1",
  "force": false
}
```

The envelope is intentionally small. The task reloads canonical input and verifies the object version/policy.

## Transactional outbox

### Write

Application service transaction:

```python
with transaction.atomic():
    domain_record = ...
    TaskOutbox.objects.create(
        command_type="signals.classify",
        payload={"signal_event_id": str(domain_record.id)},
        payload_schema_version="2.0",
        idempotency_key=idempotency_key,
        available_at=timezone.now(),
    )
```

### Dispatch

Dispatcher claims bounded rows:

```sql
SELECT ...
FROM operations_taskoutbox
WHERE published_at IS NULL
  AND available_at <= now()
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
```

It publishes each command and records `published_at`/broker message ID. Failed publication increments attempts and schedules backoff. A recovery job finds stale claims.

At-least-once delivery is expected; domain-level idempotency provides exactly-once effects.

## Task pattern

```python
@shared_task(
    bind=True,
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(TransientProviderError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
    soft_time_limit=120,
    time_limit=150,
)
def classify_signal_task(self, envelope: dict[str, object]) -> None:
    command = TaskEnvelopeV2.model_validate(envelope)
    service.execute(command)
```

Use `acks_late` and `reject_on_worker_lost` only for tasks proven idempotent. Set queue-specific soft/hard limits; do not copy one limit to deep research start/poll versus Playwright.

## Broker configuration

Recommended starting settings (domain progress is stored in PostgreSQL; do not enable a Celery result backend merely for `STARTED` state):

```python
task_serializer = "json"
accept_content = ["json"]
result_serializer = "json"
task_ignore_result = True
worker_prefetch_multiplier = 1
broker_connection_retry_on_startup = True
```

Configure Redis visibility timeout to exceed the longest single task. The design should keep single tasks short enough that a one-hour default is normally sufficient. Never send large payloads through the broker.

## Retry taxonomy

### Transient

- connection timeout/reset;
- 429 respecting provider retry-after;
- selected 5xx;
- temporary DNS/provider outage;
- broker publish failure.

### Permanent

- invalid source/schema after bounded attempts;
- unsupported provider/model/tool policy;
- blocked URL;
- missing canonical record;
- policy refusal.

### Human-required

- ambiguous duplicate merge;
- contact/route ambiguity;
- legal-route review;
- budget authorization;
- suppressed target.

A failed schema output is not endlessly repaired. At most one bounded retry/repair is allowed where the agent spec permits; otherwise fail visibly.

## Orchestration

Prefer database-driven eligibility and outbox commands over deep Celery canvas nesting. Small bounded groups are acceptable for independent fetches. Do not use a chord to represent the whole product pipeline.

## Periodic schedules

Seed idempotently through `django-celery-beat`:

```text
daily discovery
known-source refresh
outbox dispatch/recovery
deep-research polling fallback
follow-up due calculation
endpoint health and stale-source checks
research/packet invalidation
cost rollups
retention cleanup
backup freshness verification
worker/run stale detection
```

Exactly one Beat scheduler runs per environment.

## Heartbeats and stale recovery

`PipelineRun` stores heartbeat/next-poll state. Recovery must inspect domain idempotency keys and provider response IDs before retrying. It must never start a second deep-research request merely because one poll failed.

## Cancellation

- Set `cancel_requested_at` in PostgreSQL.
- Tasks check at safe boundaries.
- Request provider cancellation where supported.
- Celery revoke is an operational supplement, not the canonical cancellation state.

## Acceptance criteria

- Commit succeeds/broker fails: unpublished outbox is later delivered.
- Duplicate task delivery creates no duplicate domain effect.
- Broker/worker restart loses no canonical progress.
- Deep research occupies workers only for short start/retrieve/extract calls.
- Scheduled window runs once at domain level.
- Operations shows outbox state, attempts, next retry, and stale commands.
