# 35 — Codex Milestone Prompt Template

Use this prompt after a milestone checkpoint or when assigning a bounded subsystem to Codex.

```text
Implement milestone <NUMBER>: <NAME> for the FTL Opportunity Intelligence Platform.

GOAL
<Describe the visible, testable result of this milestone.>

READ FIRST
- `AGENTS.md`
- `README.md`
- `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`
- `PLANS.md`
- `IMPLEMENTATION_STATUS.md`
- `30_CODEX_IMPLEMENTATION_ROADMAP.md`
- `<RELEVANT NUMBERED SPECIFICATIONS>`
- `33_AGENT_PROMPT_ENGINEERING_STANDARD.md` when the milestone includes model calls

CURRENT REPOSITORY STATE
Inspect the repository and verify the previous milestone rather than assuming it is correct. Summarize existing models, migrations, services, tests, Docker services, and known failures before editing.

SCOPE
- <Required feature 1>
- <Required feature 2>
- <Required feature 3>

OWNED CONTRACTS
- Django apps/models: <...>
- Pydantic schemas: <...>
- Celery queues/tasks: <...>
- Routes/pages: <...>
- Prompt keys: <...>
- Database migrations: <...>

OUT OF SCOPE
- <Explicitly excluded future feature>
- Automatic external email sending
- Unrelated refactors

NON-NEGOTIABLES
- PostgreSQL is canonical.
- Tasks are idempotent and continue through the durable outbox.
- External text is untrusted.
- Models reference supplied evidence/source IDs only.
- Machine output uses strict Pydantic Structured Outputs.
- Human approval remains mandatory for external communication.
- No secret is committed or logged.

WORKING METHOD
1. Update `PLANS.md` with the implementation plan and validation steps.
2. Implement the smallest complete vertical slice.
3. Add migrations and tests in the same change.
4. Run all relevant checks inside Docker.
5. Update `IMPLEMENTATION_STATUS.md`, `.env.example`, commands, and documentation.
6. Inspect the final diff for placeholders, schema drift, secrets, and untested paths.

REQUIRED VALIDATION
- <Unit tests>
- <Integration tests>
- <End-to-end behavior>
- `make lint`
- `make typecheck`
- `make check-migrations`
- `make test`
- `make compose-config`
- <Additional milestone-specific commands>

DONE WHEN
- <Observable acceptance criterion 1>
- <Observable acceptance criterion 2>
- <Failure/retry criterion>
- <UI criterion>
- <Audit/provenance criterion>
- all required checks pass and their results are recorded.

FINAL REPORT
Report changed files/migrations, behavior, commands and outcomes, provider calls skipped/performed, remaining risks, and the exact next milestone. Do not claim completion without executed validation.
```
