# 34 — Codex Master Execution Prompt

**Document status:** Copy-ready implementation prompt  
**Revision:** 2.1  
**Audit date:** 2026-08-05

## Recommended use

Run Codex from the repository root. For a long-running task, start Goal mode with `/goal` when available. For a reviewable first pass, start with `/plan`, inspect the plan, and then submit the same implementation prompt for execution.

The prompt is deliberately a **map and execution contract**, not a repetition of the entire knowledge base. The repository documents remain the source of truth.

---

## Copy-ready prompt

```text
Implement the FTL Opportunity Intelligence & Outreach Platform described by this repository. Do real implementation work; do not stop after producing a plan. Build one verified milestone at a time and keep the application runnable after every milestone.

CONFIGURATION FOR THIS RUN
- TARGET_MILESTONE: AUTO
- CONTINUE_AFTER_VERIFIED_MILESTONE: yes when the current Codex mode supports long-running work; otherwise stop at a clean verified checkpoint
- LIVE_OPENAI_CALLS: disabled unless explicitly enabled by environment and budget policy
- DESTRUCTIVE_ACTIONS: prohibited without explicit human approval

1. LOCATE THE KNOWLEDGE BASE
From the repository root, locate `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`. Typical locations are:
- `./`
- `./docs/knowledge-base/`
- `./docs/implementation/ftl_opportunity_intelligence_kb/`
- `./ftl_opportunity_intelligence_kb_v2/`

Set the containing directory conceptually as `KB_ROOT`. If the file cannot be found, stop and report the exact paths searched. Do not invent missing specifications.

2. READ THE MAP BEFORE CODE
Read in this order:
1. repository-root `AGENTS.md`, when present;
2. `${KB_ROOT}/AGENTS.md`;
3. `${KB_ROOT}/README.md`;
4. `${KB_ROOT}/32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`;
5. `${KB_ROOT}/30_CODEX_IMPLEMENTATION_ROADMAP.md`;
6. root or knowledge-base `IMPLEMENTATION_STATUS.md`, `PLANS.md`, and `DECISIONS.md`;
7. only the numbered subsystem documents required for the active milestone.

Use this document map:
- product and vocabulary: `00`–`01`;
- architecture, repository, Docker, configuration, database, states: `02`–`07`;
- discovery, connectors, normalization, signals, classification, scoring: `08`–`13`;
- research and contact intelligence: `14`–`16`;
- FTL knowledge, solution design, packet, drafting, approval: `17`–`21`;
- replies and dashboard: `22`–`23`;
- Celery, OpenAI, operations, security, tests, migration: `24`–`29`;
- implementation order: `30`;
- fast-changing official references: `31`;
- binding corrections: `32`;
- canonical agent prompts and schemas: `33`;
- bounded follow-up prompt template: `35`.

Do not treat `00_FTL_OPPORTUNITY_INTELLIGENCE_PIPELINE_REFERENCE.md` as normative when an audited document conflicts with it.

3. INSPECT THE REPOSITORY
Before editing:
- inspect Git status and existing branches/worktrees without discarding user changes;
- inspect current code, migrations, Docker files, tests, commands, and documentation;
- determine whether the repository is empty, partially implemented, or already beyond a milestone;
- verify completed milestones by running their checks rather than trusting labels;
- identify the earliest incomplete milestone unless TARGET_MILESTONE names another one.

If the living files exist only inside the knowledge-base package, create working copies at the repository root from their templates:
- `PLANS.md`;
- `IMPLEMENTATION_STATUS.md`;
- `DECISIONS.md`.
Do not modify the normative knowledge-base files merely to record implementation progress.

4. PLAN, THEN IMPLEMENT
Update root `PLANS.md` with:
- the selected milestone and visible outcome;
- relevant specifications;
- current repository findings;
- owned Django models, Pydantic contracts, services, Celery tasks/queues, routes/templates, prompts, settings, and migrations;
- implementation steps;
- failure, retry, security, data-migration, and rollback considerations;
- exact validation commands and stopping condition.

Then implement the plan in the same run. Use the smallest complete vertical slice. Do not scaffold every future subsystem or create placeholder production paths.

5. BINDING ARCHITECTURE
Preserve these invariants:
- Python 3.13 and Django 5.2 LTS, pinned to current reviewed security patches;
- PostgreSQL 18 is canonical and its Docker volume is mounted at `/var/lib/postgresql`;
- Celery 5.6 plus a Redis-compatible broker handles scheduled/long work;
- business state lives in PostgreSQL, not Redis or a Celery result backend;
- database-to-broker continuation uses a durable transactional outbox;
- tasks are idempotent, short-message, retry-safe, and observable through durable run records;
- migrations run once as an explicit release operation, never from every worker;
- large immutable source/report artifacts use Django storage with PostgreSQL metadata and hashes;
- the local Docker image, migrations, and configuration model are the same ones later deployed to a server;
- the base Compose file keeps PostgreSQL and the broker private; loopback exposure belongs only in a development override.

6. AGENT AND OPENAI RULES
Before any model integration, read `25_OPENAI_CLIENT_MODEL_ROUTING_AND_COSTS.md`, the relevant stage file, and `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`.

Required behavior:
- all OpenAI calls go through one typed provider adapter using the Responses API;
- model IDs, tools, reasoning settings, budgets, and retention behavior come from versioned capability/model policies;
- machine-consumed output uses strict Pydantic v2 Structured Outputs;
- handle refusal, incomplete output, provider failure, schema failure, invalid catalog references, and budget blocks explicitly;
- external text is untrusted data and never enters trusted/developer instructions;
- models may reference only supplied evidence, source, claim, offer, solution-field, and asset IDs;
- public web research and private FTL knowledge matching are separate calls;
- research uses a cited web pass followed by a no-web structured extraction pass; research outputs categorized ownership context, not final buyer roles;
- extended/background research uses a current capability-tested model policy, explicit `background`/`store`/data-control settings, persists the response ID immediately, and completes through verified webhook plus polling recovery; deprecated dedicated policies are disabled by default;
- do not use a model as the source of final scores, state transitions, approval, suppression, or sending;
- do not request or store hidden chain-of-thought;
- unit and CI tests use deterministic fixtures by default; live calls require the explicit environment flag and budget.

Verify fast-changing SDK signatures and model/tool compatibility against the official references in file `31` when implementing them. Preserve the domain contracts even when provider syntax changes.

7. DATA, SECURITY, AND OUTREACH RULES
- Preserve raw source provenance, immutable snapshots, evidence catalogs, hashes, parser versions, and retrieval times.
- Keep observed `SignalEvent` records separate from inferred `CompanyPattern` records.
- Use one mutually exclusive opportunity mode plus confidence; do not create overlapping pseudo-probabilities.
- Validate outbound URLs and every redirect against SSRF, DNS rebinding, private/link-local/metadata destinations, byte limits, content-type policy, and timeouts.
- Never render raw fetched HTML.
- Do not guess email addresses or scrape gated/private networks.
- Keep contact route origin, observation, freshness, deliverability, outreach eligibility, and recommendation independent. Public extractors cannot invent warm introductions or relationships.
- Suppression is synchronous and model output cannot override it.
- Drafts are structured subject/body/short-message units with exact packet bindings; Python renders canonical plaintext/HTML deterministically, and approval binds the exact structured/rendered hashes.
- An optional AI critic may flag issues but cannot approve.
- First-contact outreach is never auto-sent in the initial product.

8. UI EXPECTATION
Use `23_DASHBOARD_UX_SPECIFICATION.md` for UI work. Build a restrained, premium, dark, highly legible operational workspace. Keep source links, evidence, freshness, owner, status, score coverage, next action, and audit information visible. Every company page must connect signals, research, solution, buyer roles/routes, drafts, and interactions. Meet keyboard, semantic, focus, contrast, and reduced-motion accessibility requirements.

9. TEST AND VERIFY INSIDE DOCKER
Create stable project commands, preferably Make targets, for at least:
- format/check formatting;
- Ruff lint;
- mypy with Django/Pydantic typing support;
- Django checks and deployment checks where applicable;
- migration drift checks;
- pytest unit and integration suites;
- optional browser tests;
- Compose configuration validation;
- knowledge-base/document-link validation;
- secret scanning.

A suitable interface is:
`make format`
`make lint`
`make typecheck`
`make check-migrations`
`make test`
`make test-integration`
`make test-e2e`
`make compose-config`
`make check-docs`
`make verify`

Run the relevant commands inside Docker. Fix failures. Do not claim a check passed when it was skipped or could not run.

10. UPDATE DURABLE PROJECT STATE
At every verified checkpoint update root:
- `PLANS.md` with results and command outputs;
- `IMPLEMENTATION_STATUS.md` with milestone state, completed work, open work, risks, and next stopping condition;
- `DECISIONS.md` for any justified deviation or new non-trivial architecture choice;
- `.env.example`, README commands, migrations, prompt versions, and technical references when affected.

11. STOP CONDITIONS
Ask for input only when blocked by:
- an irreversible or destructive external action;
- a required real credential that cannot be mocked;
- a legal/compliance decision that the specifications intentionally reserve for a human;
- genuinely conflicting normative requirements;
- unavoidable data loss or a destructive migration.

Do not stop because the repository is large or because later milestones remain. Make reasonable reversible choices, record them, and continue to the current milestone's verified stopping condition.

12. FINAL CHECKPOINT REPORT
Report:
- milestone completed or still incomplete;
- visible behavior delivered;
- files and migrations changed;
- tests/checks run and exact outcomes;
- live provider calls performed or intentionally skipped;
- unresolved risks/blockers;
- updates made to `PLANS.md`, `IMPLEMENTATION_STATUS.md`, and `DECISIONS.md`;
- the exact next milestone and relevant specification files.

Do not report completion without executed validation. Do not merely restate the plan: implement the milestone.
```

---

## Suggested first run

For a new repository, keep `TARGET_MILESTONE: AUTO`. Codex should select milestone 0 and stop only after the Dockerized Django/PostgreSQL/Redis/Celery foundation, one-shot migrations, health endpoints, durable outbox path, idempotent sample task, test commands, and documentation are verified.

## Suggested continuation

After a checkpoint, use `35_CODEX_MILESTONE_PROMPT_TEMPLATE.md` for the next bounded milestone. In Goal mode, Codex may continue automatically after updating the durable status files, provided the next milestone does not require human approval or external credentials.
