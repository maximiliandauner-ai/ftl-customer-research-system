# FTL Opportunity Intelligence & Outreach Platform

Local-first opportunity intelligence for Faster Than Light. The audited implementation specification lives in [`docs/ftl-opportunity-intelligence/`](docs/ftl-opportunity-intelligence/README.md), and the current software checkpoint is recorded in [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md).

## License

This project is source-available under the PolyForm Noncommercial License 1.0.0.

Commercial use, commercial deployment, integration into commercial products or services, and use for commercial purposes require a separate written licence from Faster Than Light.

For commercial licensing enquiries, contact: maximilian.dauner@ftl.vision

## Quick start

Requirements: Docker Engine with Compose v2. The runtime and all quality checks use Docker; the host-only bootstrap helper uses Python solely to generate local development secrets.

```sh
make bootstrap
make up
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

`make bootstrap` creates `.env` only when absent, gives it restrictive permissions, and builds the reviewed images. `make up` starts PostgreSQL and Redis, runs migrations once through the explicit release service, then starts web, workers, Beat, and the proxy. PostgreSQL and Redis are private in the base stack; the development override exposes them on loopback only.

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) after creating an operator and assigning one canonical FTL role:

```sh
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web python manage.py createsuperuser
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web \
  python manage.py assign_team_role <username> founder --reason initial_local_access
```

The authenticated workspace exposes discovery, company, public-source, canonical-job, observed-signal, ranked-opportunity, pipeline-run, outbox, and append-only audit pages. Researchers, founders, and administrators may run a versioned search or submit a confirmed public source. Reviewers may retract a false-positive signal or record separate assessment/qualification overrides with audited reasons; viewers and researchers have read-only signal and opportunity access.

Queue either reviewed search family from `/discovery/` or from the command line:

```sh
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web \
  python manage.py run_discovery --definition-key ftl-capability-demand
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web \
  python manage.py run_discovery --definition-key ftl-creative-learning-demand
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web \
  python manage.py run_discovery --definition-key ftl-learning-enablement-demand
```

Every discovery run is first committed to PostgreSQL with its logical window, immutable search-definition version, limits, audit event, and outbox command. The operations family covers workflow/data/knowledge demand. Narrow German/English creative-video and learning-enablement families cover AI-assisted production, learning content, AI tutoring, internal enablement, and nonstandard part-time role titles without hardcoding employers; their yield can be measured independently instead of being diluted in one oversized query. Newly registered endpoints become watched sources, and known endpoints are polled through the same safe fetch/parse path even when OpenAI is disabled. New web-search candidates require all three of `OPENAI_ENABLED=1`, `WEB_SEARCH_ENABLED=1`, and a real `OPENAI_API_KEY`; per-run, daily, monthly, and concurrency limits are enforced from the active database policy and runtime settings. The default configuration keeps those calls disabled.

Submit the first public source in the UI at `/sources/submit/`, or through the audited command:

```sh
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web \
  python manage.py submit_public_source https://api.ashbyhq.com/posting-api/job-board/Ashby \
  --username <username> \
  --company-name "Ashby" \
  --company-domain ashbyhq.com \
  --confirm-public
```

Submission first validates the URL, hostname, DNS answers, and public-source confirmation. One PostgreSQL transaction then creates the candidate, endpoint, pipeline run, audit event, and outbox command. Beat publishes the command to the `fetch` queue; the worker revalidates DNS and every redirect, pins TCP to validated public addresses, enforces TLS, content-type, byte, redirect, and timeout limits, and records every attempt. A changed immutable source snapshot atomically queues a separate `jobs.normalization` run on the `parse` queue. Deterministic Personio, Greenhouse, Lever, Ashby, JobPosting JSON-LD, and conservative generic-HTML connectors then create canonical jobs, locations, immutable normalized snapshots, and exact observations. Known-provider schema errors never fall back to generic parsing and never close prior jobs.

Metadata, searchable normalized fields, hashes, lifecycle state, provenance, and audit remain in PostgreSQL. The immutable response body is saved through Django storage (the local `media_data` volume), with its storage key and SHA-256 in PostgreSQL; raw fetched HTML is never rendered. Follow the result from `/sources/` to its endpoint and parse run, or inspect all canonical postings at `/jobs/`. Processing normally completes within two outbox-dispatch intervals (about 20 seconds with the default local schedule).

Eligible created/material/reopened/closed job events automatically queue deterministic observed-signal detection on the `classification` queue. The worker builds an immutable exact-text evidence catalog, records an explicit signal or no-signal outcome, and exposes active results at `/signals/`. Search snippets never enter evidence. Generic `AI` text and instruction-like source segments do not create capability signals. The default path needs no model credential; live OpenAI calls remain disabled. Existing eligible events can be queued idempotently after a detector-policy upgrade:

```sh
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web \
  python manage.py backfill_signal_detection --limit 500
```

Active observed signals automatically continue through evidence-bound capability classification and deterministic company aggregation. Python computes scores and coverage; provider/model output cannot qualify or send. Inspect current ranking at `/opportunities/`. Existing active signals can be queued idempotently for classification after a policy rollout:

```sh
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web \
  python manage.py backfill_signal_classification --limit 500
```

Research-eligible and qualified opportunity pages expose an explicit company-research action to permitted operators. The action first commits a versioned brief, pipeline run, audit event, and ID-only outbox command to PostgreSQL. A cited public-web pass stores the plain-text report through Django storage and registers each provider-derived URL as a local `SRC-` record; a separate no-web Structured Output pass may then create only claims bound to supplied source, signal, and evidence IDs. PostgreSQL stores all report metadata, hashes, citations, claims, dossier text, freshness, failures, and history; database triggers protect research evidence from mutation. Provider HTML is never rendered.

Live standard research requires all of `OPENAI_ENABLED=1`, `WEB_SEARCH_ENABLED=1`, `STANDARD_RESEARCH_ENABLED=1`, a real `OPENAI_API_KEY`, reviewed active database policies, and sufficient run/daily/monthly budget. Restart the web and workers after changing runtime configuration. The checked-in default keeps this disabled, while deterministic tests exercise the complete report-to-dossier path without provider egress. Research status and any completed results are visible at `/research/`. No email is generated or sent.

FTL offers, claims, and outreach assets live in the reviewed `knowledge_base/` editorial tree and are imported as immutable database releases. Validate and append the current files without activating them:

```sh
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web \
  python manage.py sync_ftl_knowledge --commit <git-commit-sha> --validate --username <founder-or-admin>
```

Review that release at `/knowledge/`, then activate its displayed UUID as a separate audited human action:

```sh
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web \
  python manage.py activate_ftl_knowledge <release-uuid> \
  --username <founder-or-admin> --reason "Reviewed editorial release"
```

The starter catalog intentionally has no approved claims or assets; add only real reviewed collateral metadata rather than placeholder proof. A completed current research dossier plus an active knowledge release enables “Design solution & match assets” on the opportunity page. The service creates an immutable evidence-bound phased solution, then records a valid zero-to-two asset result after filtering confidentiality, publication status, external approval, audience, language, freshness, and link health. Results and exact hashes are saved in PostgreSQL and visible at `/solutions/`. No email content is created or sent.

After a solution is human-approved, the opportunity page can queue “Research buyer roles & public routes.” A fresh `make bootstrap` already generates separate protected-route encryption and HMAC keys. For an `.env` created before this feature existed, generate only its missing keys without printing or replacing existing secrets, then enable the scanner and restart the application:

```sh
make bootstrap-contact-keys
# Edit .env: CONTACT_ROUTE_RESEARCH_ENABLED=1
make up
```

The role step deterministically maps the approved solution’s exact responsibilities to evidence-bound buyer-role categories; it does not invent people or addresses. The scanner then fetches only registered `official_company` research sources on the known company domain through the same DNS/redirect/size/timeout-safe client. It accepts only literal public `mailto:`, `tel:`, form-action, and contact-link observations, and a valid run may find none. Source bodies, sensitive evidence fragments, and protected route values are encrypted; PostgreSQL stores their durable metadata, hashes, masked displays, state, and audit history while Django storage holds the encrypted source artifact.

Review route origin, freshness, deliverability, outreach eligibility, legal status, recommendation, and suppression independently at `/contacts/`. An authorized reviewer may select an exact eligible, legally approved, unsuppressed route for future work. Public parsing cannot claim a warm introduction or existing relationship, and this release deliberately creates no packet, draft, email, or send record.

Detailed dependency health is permissioned at `/health/dependencies`; public liveness and readiness reveal only bounded status.

Stop without deleting data:

```sh
make down
```

The destructive `make destroy` target is guarded and is never part of normal development or verification.

## Quality interface

```sh
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
```

Quality commands run in the Docker `quality` image. Deterministic tests use fixtures and local services only. Live OpenAI calls are disabled by default and require explicit feature flags, a real credential, and the active reviewed model policy; verification never enables them.

## Database operations

```sh
make migrate
make backup
make restore-drill FILE=backups/<timestamp>/database.dump
```

Backups include a PostgreSQL custom-format dump, the local media volume archive, a manifest, and SHA-256 checksums. `restore-drill` restores into an isolated temporary PostgreSQL 18 container and never touches the canonical database. Direct restore into the development PostgreSQL service requires a new database name and refuses an existing target.

## Compose layouts

- `compose.yaml`: private data services and the shared application topology.
- `compose.dev.yaml`: source mounts and loopback-only developer ports.
- `compose.prod.yaml`: immutable prebuilt image, TLS proxy, read-only app roots, dropped capabilities, and no public database/broker ports.

Production startup requires real secrets, HTTPS hosts/origins, and an immutable `APP_IMAGE` tag or digest. See [`.env.example`](.env.example) and [`docs/ftl-opportunity-intelligence/05_CONFIGURATION_AND_SECRETS.md`](docs/ftl-opportunity-intelligence/05_CONFIGURATION_AND_SECRETS.md).
