# 03 — Repository and Django Application Structure

**Specification version:** 2.1  
**Primary owner:** Backend architecture

## Purpose

Define a repository structure that makes domain ownership, integration boundaries, prompts, operations, and vertical milestones explicit.

## Required layout

```text
ftl-opportunity-radar/
├── AGENTS.md
├── README.md
├── IMPLEMENTATION_STATUS.md
├── DECISIONS.md
├── CHANGELOG.md
├── pyproject.toml
├── uv.lock or equivalent lock file
├── manage.py
├── Dockerfile
├── compose.yaml
├── compose.dev.yaml
├── compose.prod.yaml
├── .env.example
├── Makefile
├── config/
│   ├── celery.py
│   ├── urls.py
│   ├── wsgi.py
│   ├── asgi.py
│   └── settings/{base,local,test,production}.py
├── apps/
│   ├── core/
│   ├── accounts/
│   ├── companies/
│   ├── sources/
│   ├── jobs/
│   ├── signals/
│   ├── opportunities/
│   ├── research/
│   ├── contacts/
│   ├── knowledge/
│   ├── outreach/
│   ├── interactions/
│   ├── operations/
│   └── analytics/
├── domain/
│   ├── enums/
│   ├── schemas/
│   ├── scoring/
│   ├── policies/
│   └── canonicalization/
├── services/
│   ├── discovery/
│   ├── ingestion/
│   ├── classification/
│   ├── aggregation/
│   ├── research/
│   ├── solution_design/
│   ├── asset_matching/
│   ├── contacts/
│   ├── packet_building/
│   ├── drafting/
│   ├── review/
│   ├── interactions/
│   └── outbox/
├── integrations/
│   ├── openai/
│   ├── personio/
│   ├── greenhouse/
│   ├── lever/
│   ├── ashby/
│   ├── generic_web/
│   ├── storage/
│   └── email/
├── prompts/
│   ├── registry.py
│   └── versions/<prompt_key>/<semver>/{developer.md,user_template.md,metadata.yaml,CHANGELOG.md}
├── knowledge_base/
├── templates/
├── static/
├── tests/{unit,integration,contract,e2e,fixtures,evals}/
├── scripts/
└── docs/implementation/  # this knowledge base when embedded in the repo
```

## App ownership

| App | Owns |
|---|---|
| `core` | UUID/time mixins, audit primitives, common validators |
| `accounts` | users, roles, permissions |
| `companies` | canonical company, domain, alias, company pattern/assessment |
| `sources` | source endpoint, candidate, fetch observation, artifact metadata |
| `jobs` | job posting, snapshot, location, duplicate relationship |
| `signals` | observed signal event/evidence and signal assessment/gaps |
| `opportunities` | opportunity, solution hypothesis, owner, stage, next action |
| `research` | brief, run, report, claim, source, citation binding |
| `contacts` | buyer-role hypothesis, contact observation, route, suppression |
| `knowledge` | FTL release, offer module, asset, approved/prohibited claim |
| `outreach` | packet, structured draft units/bindings, rendering, review, approval |
| `interactions` | immutable message/note/meeting, reply assessment, follow-up |
| `operations` | pipeline run, provider call, usage/cost, task outbox, webhook event |
| `analytics` | read models and materialized/reporting queries only |

## Dependency direction

```text
views/forms/admin/management commands/Celery tasks
    -> application services
        -> domain policies/schemas/scoring
            -> ORM repositories and integration adapters
```

Forbidden dependencies:

- integrations importing Django views;
- models calling Celery directly;
- prompts querying the ORM;
- analytics mutating canonical records;
- tasks containing orchestration/business rules;
- service code importing templates;
- provider response objects leaking outside integration adapters.

## Service pattern

```python
@dataclass(frozen=True)
class ClassifySignalCommand:
    signal_event_id: UUID
    prompt_version: str
    model_policy_version: str
    force: bool = False

class SignalClassificationService:
    def execute(self, command: ClassifySignalCommand) -> SignalAssessment:
        ...
```

Services return domain records or versioned Pydantic outcomes. They write audit and outbox records in the same transaction where required.

## Prompt registry

Every active prompt has:

```yaml
key: capability_gap_classifier
version: 2.0.0
output_schema: CapabilityGapClassificationV2
model_policy_key: high_volume_structured
input_contract: CapabilityGapClassifierInputV2
status: active
knowledge_access: public_signal_only
web_access: false
```

A semantic prompt change increments the prompt version and requires local evaluation before activation. Prompt text is never embedded ad hoc in services.

## Package and dependency policy

- Pin direct dependencies and commit a resolved lock file.
- Keep optional Playwright/browser dependencies in a separate image target or dependency group.
- Use `ruff`, `mypy`, `django-stubs`, `pytest`, and `pytest-django`.
- Avoid repository abstractions that only wrap one ORM call without adding policy or test value.
- Prefer explicit application services over generic event-bus magic.

## Acceptance criteria

- The scaffold runs before feature work.
- Import-boundary tests prevent forbidden dependencies.
- Each Django app has an ownership README.
- Business operations execute through services without HTTP.
- Management commands, tasks, and UI call the same services.
- Prompt/version metadata can be inspected in Operations.
