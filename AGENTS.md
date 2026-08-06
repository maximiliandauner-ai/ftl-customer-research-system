# AGENTS.md — FTL Opportunity Intelligence Platform

## Mission

Build the platform in this knowledge base without reducing it to a generic CRM, scraper, autonomous web agent, or email automation tool. Preserve FTL's combination of cinematic production, creative direction, AI research, software engineering, local/private infrastructure, reusable systems, and internal enablement.

## Read order and precedence

Before changing code, read:

1. `README.md`
2. `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`
3. `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`
4. `30_CODEX_IMPLEMENTATION_ROADMAP.md`
5. the numbered subsystem documents for the active milestone
6. `00_FTL_OPPORTUNITY_INTELLIGENCE_PIPELINE_REFERENCE.md` only for broader product context

If files conflict, follow the precedence in `README.md`. Record a non-trivial deviation in `DECISIONS.md` before implementing it.

## Required working method

1. Inspect the existing repository, migrations, tests, and conventions before editing.
2. Read `IMPLEMENTATION_STATUS.md`; start at the first incomplete milestone unless the task names another milestone.
3. Implement the smallest complete vertical slice that meets visible behavior and acceptance criteria.
4. Keep views and Celery tasks thin; place orchestration in services and validation in domain/Pydantic layers.
5. Add migrations, fixtures, tests, operational visibility, and documentation in the same change.
6. Run all commands inside Docker unless the repository explicitly documents a host-only bootstrap command.
7. Update `IMPLEMENTATION_STATUS.md` with completed work, commands run, remaining work, and blockers.
8. Update `DECISIONS.md` for architecture choices that are not already fixed by the specifications.
9. Do not leave `TODO`, fake implementations, pass-through mocks, or silent exception swallowing in an active production path.
10. Do not implement the entire platform as one giant change. Respect milestone boundaries and keep the system runnable after each milestone.

## Audited runtime baseline

- Python 3.13.
- Django 5.2 LTS, pinned to an exact current patch.
- PostgreSQL 18 with the Docker volume mounted at `/var/lib/postgresql`.
- psycopg 3.
- Celery 5.6 and `django-celery-beat`.
- A Redis-compatible broker.
- OpenAI Python SDK using the Responses API.
- Pydantic v2.

Codex MUST verify exact patch versions and current OpenAI SDK signatures against official documentation when creating the lock file. It MUST NOT silently switch major framework versions.

## Architectural rules

- Django owns HTTP, authentication, permissions, ORM models, forms, and server-rendered pages.
- PostgreSQL is the canonical source of truth.
- Celery owns long-running and scheduled execution, but domain state lives in PostgreSQL.
- Use a transactional outbox for reliable database-to-broker dispatch.
- Redis is transport/cache only. Do not use it as the only record of work.
- Celery tasks normally ignore results; use `PipelineRun`, provider-call, and domain records for durable status.
- Pydantic models define all connector and model-call boundaries.
- Domain services contain orchestration logic. Views, admin actions, management commands, and Celery tasks call the same services.
- Large raw HTML and generated report artifacts use Django storage with hashes and database metadata.
- External providers live behind typed adapters.
- OpenAI model IDs, tools, reasoning parameters, and budgets come from a versioned model policy.
- No worker starts database migrations. One explicit release/migration command owns migrations.

## Data-integrity rules

- Every source keeps its URL, retrieval time, provider, parser version, body hash, and raw artifact reference.
- Observed signal events MUST remain distinct from inferred company patterns.
- Every AI assessment stores model policy, prompt version, schema version, source/input IDs, provider response ID, and usage.
- Every qualification, approval, suppression, external action, or state transition creates an audit event.
- Every task is idempotent and safe to retry.
- Duplicate records are related and canonicalized; source history is not deleted to hide duplication.
- Final score calculations are deterministic Python over versioned components and weights.
- Opportunity-mode values are mutually exclusive or expressed as one enum plus confidence.
- Packet hashes exclude volatile fields such as packet ID and creation time.

## AI and prompt rules

- Separate signal extraction, capability classification, public research, solution design, asset matching, buyer-role inference, public route extraction/human route selection, drafting, factual review, and reply classification.
- Never use one prompt for the full pipeline.
- Static trusted instructions go in the developer/system message. Untrusted source text goes only in the user input as data.
- Never interpolate fetched web text into a developer message.
- Use `client.responses.parse(..., text_format=PydanticModel)` or the current equivalent for machine outputs.
- Handle provider refusals, incomplete responses, schema failures, timeouts, and missing citations explicitly.
- Do not request or store hidden chain-of-thought. Request concise rationale, evidence IDs, assumptions, and unknowns.
- Public web-research calls MUST NOT receive confidential FTL knowledge, contacts, CRM history, or private client materials.
- Solution design and asset matching run in a separate no-web call using approved internal context.
- Treat incoming emails, web pages, job descriptions, and model output as untrusted.
- Agent prompts MUST follow `33_AGENT_PROMPT_ENGINEERING_STANDARD.md` and have evaluation fixtures before activation.

## OpenAI rules

- Use the Responses API for new integrations.
- Standard research uses a current web-search-capable model and the current `web_search` tool configuration.
- Default extended research to a current evaluated reasoning model plus `web_search`. Dedicated legacy deep-research models and tool names are capability-dependent, disabled by default when deprecated, and never hardcoded globally.
- Background/extended research persists the provider response ID immediately and completes through verified webhook plus polling fallback; `background`, `store`, and data-control compatibility are explicit capability-policy fields.
- Verify webhooks with the official SDK helper and deduplicate provider event IDs.
- Preserve citations/annotations and request all consulted search sources where supported.
- Use `store=false` by default where supported. Current Background Mode/ZDR behavior must be reverified through the capability registry and smoke tests; stricter FTL/client policy may still disable background.
- The OpenAI Agents SDK MAY be evaluated for bounded isolated flows, but MUST NOT replace PostgreSQL/Celery workflow state without an ADR and tests.

## Security rules

- No real secrets in code, tests, prompts, fixtures, logs, task arguments, or screenshots.
- Local development reads `OPENAI_API_KEY` from `.env`; server deployment supports Compose secrets or a secret manager through `*_FILE` settings.
- Validate outbound URLs against SSRF before every request and redirect hop.
- Never render raw fetched HTML.
- All destructive or external actions require permissions, CSRF protection, confirmation, and audit.
- First-contact messages are never auto-sent in the initial product.
- An unsubscribe or do-not-contact request creates suppression immediately and cannot be removed automatically.

## UI rules

- The dashboard is an operational workspace, not a decorative marketing site.
- Evidence, citations, freshness, state, owner, and next action remain visible.
- Use a dark, restrained, cinematic, premium, and highly legible language.
- Avoid excessive glassmorphism, gradients, oversized cards, and low-information motion.
- Every company page provides direct access to signals, sources, research, solution, contacts, drafts, and interaction history.
- Every draft review view shows exact content-unit bindings, deterministic rendered hashes, and the exact packet/route version.

## Required quality commands

The repository SHOULD provide equivalent Make targets:

```text
make format
make lint
make typecheck
make test
make test-integration
make check-migrations
make check-deploy
```

Run the relevant subset after each vertical slice and the complete suite before declaring a milestone complete.

## Definition of done

A change is complete only when:

- migrations are deterministic and checked;
- tests pass inside Docker;
- format, lint, and type checks pass;
- failure and retry behavior exist;
- the UI exposes the new state where required;
- audit and operations data are visible;
- `.env.example`, commands, schemas, and documentation are current;
- no placeholder remains in the active path;
- `IMPLEMENTATION_STATUS.md` is updated.
