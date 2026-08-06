# 26 — Observability and Operations

**Specification version:** 2.1  
**Primary owner:** Operations

## Purpose

Make requests, outbox dispatch, Celery work, source fetching, model calls, research, approvals, backups, failures, and costs diagnosable from structured logs and the dashboard.

## Logging

Production logs are JSON; local logs are readable but contain the same fields.

Required fields:

```text
timestamp
level
service
event
request_id
user_id nullable
pipeline_run_id nullable
outbox_id nullable
celery_task_id nullable
object_type/object_id nullable
provider/operation nullable
attempt
duration_ms
status
error_code nullable
```

Never log secrets, auth/cookie headers, full contact exports, raw inbound emails, confidential prompts, or full fetched bodies. Log hashes/artifact IDs instead.

## Correlation

- Reverse proxy/Django creates or accepts a safe request ID.
- Services propagate it to `PipelineRun`, `TaskOutbox`, Celery headers/envelope, and `ProviderCall`.
- Provider request/response IDs are linked but not used as the application request ID.

## PipelineRunV2

```text
pipeline_name
stage
status queued|running|waiting_external|complete|failed|cancelled
trigger scheduled|manual|backfill|webhook|recovery
requested_by nullable
started_at/completed_at/heartbeat_at/next_action_at
input/output/warning/error counts
policy versions
estimated/actual cost
context jsonb (safe IDs only)
```

## Health endpoints

```text
/health/live          process responds; public minimal
/health/ready         database, migrations, writable storage; public minimal
/health/dependencies  authenticated detailed database/broker/workers/beat/outbox/OpenAI/storage/source health
```

OpenAI outage should not make the web process unready unless the endpoint represents an AI worker specifically.

## Operational metrics

### Ingestion

- fetches by provider/status;
- SSRF/robots/size blocks;
- parser failures/version;
- candidate-to-posting yield;
- snapshot/change/duplicate counts.

### Intelligence

- signal/classification schema pass rate;
- relevance and routing distribution;
- evidence validation failure;
- company patterns/assessment backlog.

### AI/research

- calls by stage/model/prompt;
- token/tool/source usage;
- latency, refusal, incomplete, schema failure;
- standard/deep research duration;
- webhook duplicates/invalid signatures;
- cost by company/opportunity/stage.

### Workflow

- queue depth;
- worker/Beat heartbeats;
- unpublished/stale outbox rows;
- retries/dead-letter-like failed commands;
- stale pipeline runs;
- approval/follow-up backlog.

### Resilience

- last successful backup and restore drill;
- artifact storage usage;
- retention deletion failures.

## Error taxonomy

Use stable error codes, for example:

```text
FETCH_TIMEOUT
FETCH_BLOCKED_SSRF
FETCH_ROBOTS_BLOCKED
FETCH_RESPONSE_TOO_LARGE
PARSE_SCHEMA_MISSING
NORMALIZATION_FAILED
DUPLICATE_CONFLICT
OUTBOX_PUBLISH_FAILED
TASK_STALE
OPENAI_RATE_LIMITED
OPENAI_REFUSAL
OPENAI_INCOMPLETE
OPENAI_SCHEMA_INVALID
OPENAI_TOOL_POLICY_INVALID
WEBHOOK_SIGNATURE_INVALID
RESEARCH_RESPONSE_EXPIRED
RESEARCH_STALE
CONTACT_ROUTE_STALE
CONTACT_SUPPRESSED
APPROVAL_INVALIDATED
BACKUP_VERIFICATION_FAILED
```

## Alerts

At minimum:

- missed daily discovery;
- worker or Beat missing;
- outbox oldest unpublished age above threshold;
- repeated connector failures;
- high-priority review backlog;
- invalid webhook signature spike;
- daily/monthly cost threshold;
- overdue/failed backup;
- artifact disk pressure;
- external provider disabled.

Local development may display alerts only in Operations. Server deployment SHOULD send an email or another team-owned channel.

## Safe retry

Operations allows retry only when the stored error taxonomy/policy marks it eligible. The retry UI shows idempotency key, previous attempts, affected record, and whether an external provider request already exists. Human-required failures use a resolution workflow, not blind retry.

## Optional metrics stack

Start with database-backed operational pages and structured logs. Prometheus/Grafana/OpenTelemetry MAY be added as a Compose profile once operational volume justifies it. Do not block the first release on a separate observability stack.

## Acceptance criteria

- A failed pipeline stage is diagnosable without shell/container logs.
- Every external call and task correlates to a domain record.
- Outbox backlog and deep-research waiting state are visible.
- Public health endpoints expose no sensitive detail.
- Eligible retries are safe and audited.
- Cost can be attributed to a stage and opportunity/company where applicable.
