# 31 — Primary Technical References and Version-Recheck Rules

**Specification version:** 2.1  
**Primary owner:** Engineering  
**Audit date:** 2026-08-05

## Purpose

List primary official documentation that Codex must consult for fast-changing provider/framework syntax. Domain contracts and architectural boundaries are fixed by this knowledge base; exact SDK signatures, model/tool availability, patch versions, container tags, and retention behavior must be reverified during implementation and upgrades.

Raw links are intentionally present in this engineering document for Codex.

## OpenAI

- Model catalog: https://developers.openai.com/api/docs/models
- Latest-model guidance: https://developers.openai.com/api/docs/guides/latest-model
- Responses API: https://developers.openai.com/api/docs/guides/responses
- Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Web search: https://developers.openai.com/api/docs/guides/tools-web-search
- Deep research: https://developers.openai.com/api/docs/guides/deep-research
- Background Mode: https://developers.openai.com/api/docs/guides/background
- Webhooks: https://developers.openai.com/api/docs/guides/webhooks
- Batch: https://developers.openai.com/api/docs/guides/batch
- Safety best practices: https://developers.openai.com/api/docs/guides/safety-best-practices
- Agents SDK: https://openai.github.io/openai-agents-python/
- Evals/deprecation guidance: https://developers.openai.com/api/docs/guides/evals

### Audited provider notes

- Current model documentation lists GPT-5.6 Luna, Terra, and Sol. Treat names as model-policy seed values, not business constants.
- Current web-search guidance uses the Responses API `web_search` tool; legacy preview tool shapes must not be copied into new code.
- Current model-catalog documentation marks `o3-deep-research` and `o4-mini-deep-research` as deprecated, while dedicated deep-research guidance may remain available. Default to evaluated current reasoning models plus `web_search`; legacy dedicated policies require live capability verification.
- Current Background Mode guidance documents `store=false` support for Zero Data Retention projects with a short temporary retrieval window. Recheck the exact behavior before enabling it.
- Structured Outputs require explicit refusal/incomplete handling and schema validation.
- Webhooks require official signature verification on the raw body and event deduplication; retrieve the canonical response by ID.
- OpenAI currently documents the legacy Evals API as read-only after 2026-10-31 and shut down after 2026-11-30. The FTL local evaluation harness remains canonical.

## Codex

- Codex overview/documentation: https://developers.openai.com/codex/
- Best practices: https://developers.openai.com/codex/learn/best-practices
- AGENTS.md guidance: https://developers.openai.com/codex/guides/agents-md
- Long-running/Goal-mode guidance: https://developers.openai.com/codex/
- Changelog: https://developers.openai.com/codex/changelog

Implementation rule: Codex reads repository `AGENTS.md`, uses `PLANS.md`/`IMPLEMENTATION_STATUS.md` for long-running work, inspects existing code before editing, implements one verified milestone at a time, and reports executed checks rather than only a plan.

## Django

- Supported versions/download page: https://www.djangoproject.com/download/
- Django 5.2 documentation: https://docs.djangoproject.com/en/5.2/
- Deployment checklist: https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
- Security: https://docs.djangoproject.com/en/5.2/topics/security/
- PostgreSQL backend: https://docs.djangoproject.com/en/5.2/ref/databases/
- Settings: https://docs.djangoproject.com/en/5.2/topics/settings/

Audited baseline: Python 3.13 and latest reviewed Django 5.2 LTS security patch (5.2.17 at the audit date), supported through April 2028. Reassess Django 6.2 LTS through an ADR after release/ecosystem validation.

## Celery

- Stable documentation: https://docs.celeryq.dev/en/stable/
- Django integration: https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html
- Tasks/retries: https://docs.celeryq.dev/en/stable/userguide/tasks.html
- Calling/retry policy: https://docs.celeryq.dev/en/stable/userguide/calling.html
- Workers: https://docs.celeryq.dev/en/stable/userguide/workers.html
- Configuration: https://docs.celeryq.dev/en/stable/userguide/configuration.html
- Brokers/backends: https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/

Audited baseline: Celery 5.6.3. Canonical progress lives in PostgreSQL; tasks normally use `ignore_result=True` and a durable outbox/idempotency contract.

## PostgreSQL, Redis, and Docker

- Docker Compose: https://docs.docker.com/compose/
- Compose production: https://docs.docker.com/compose/how-tos/production/
- Startup order: https://docs.docker.com/compose/how-tos/startup-order/
- Compose secrets: https://docs.docker.com/compose/how-tos/use-secrets/
- Build secrets: https://docs.docker.com/build/building/secrets/
- Volumes: https://docs.docker.com/engine/storage/volumes/
- Official PostgreSQL image: https://hub.docker.com/_/postgres
- PostgreSQL current docs: https://www.postgresql.org/docs/current/
- pg_dump: https://www.postgresql.org/docs/current/app-pgdump.html
- pg_restore: https://www.postgresql.org/docs/current/app-pgrestore.html
- Redis releases: https://github.com/redis/redis/releases
- Official Redis image: https://hub.docker.com/_/redis

Audited baseline: PostgreSQL 18.4 and Redis 8.10.0. PostgreSQL 18+ official images mount persistent data at `/var/lib/postgresql`; PostgreSQL 17 and below used `/var/lib/postgresql/data`. Verify image tags/digests before locking them.

## Public job providers

- Personio open-position XML: https://developer.personio.de/v1.0/reference/get_xml
- Greenhouse Job Board API: https://developers.greenhouse.io/job-board.html
- Lever Postings API: https://github.com/lever/postings-api or current official Lever documentation
- Ashby public job posting API: https://developers.ashbyhq.com/docs/public-job-posting-api
- Schema.org JobPosting: https://schema.org/JobPosting
- Google JobPosting structured data: https://developers.google.com/search/docs/appearance/structured-data/job-posting

Verify provider terms, feed enablement, pagination, localization, rate limits, and endpoint shapes before implementation.

## Security and legal source texts

- OWASP SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP Top 10 SSRF: https://owasp.org/Top10/2021/A10_2021-Server-Side_Request_Forgery_%28SSRF%29/
- German UWG: https://www.gesetze-im-internet.de/uwg_2004/
- GDPR: https://eur-lex.europa.eu/eli/reg/2016/679/oj

The platform safeguards do not replace route- and country-specific legal advice.

## Libraries

- Pydantic: https://docs.pydantic.dev/
- HTTPX: https://www.python-httpx.org/
- HTMX: https://htmx.org/docs/
- Tailwind CSS: https://tailwindcss.com/docs
- Playwright Python: https://playwright.dev/python/docs/intro
- psycopg 3: https://www.psycopg.org/psycopg3/docs/

## Verification rule

Codex MUST record exact installed versions, capability-smoke-test dates, and important provider decisions in the repository lock file and `DECISIONS.md`. A syntax example in this knowledge base never overrides newer official documentation when the domain contract can be preserved. Any material provider/framework behavior change requires tests and, where architectural, an ADR.
