# 05 — Configuration, Secrets, Feature Flags, and Provider Policies

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Platform and security  
**Audience:** Codex and FTL engineers

## 1. Purpose

Define typed runtime configuration, environment separation, secret loading, feature flags, OpenAI model policies, and startup validation.

## 2. Configuration principles

1. Environment-specific values come from environment variables or mounted secret files.
2. Stable business ontologies and prompts remain version-controlled.
3. Editable operational policies may be stored in PostgreSQL with versioning and audit.
4. Secrets never enter task payloads, prompts, templates, audit descriptions, URLs, or logs.
5. Production startup fails closed on unsafe or missing critical settings.
6. Local development can run without external-provider credentials when the corresponding feature is disabled.

## 3. Settings implementation

Use layered Django settings:

```text
config/settings/
  base.py
  development.py
  test.py
  production.py
```

Environment parsing MUST be typed and centralized. Use one reviewed library or a small explicit parser; do not scatter `os.getenv()` through business code.

Recommended structure:

```python
@dataclass(frozen=True)
class OpenAISettings:
    enabled: bool
    api_key: SecretStr | None
    webhook_secret: SecretStr | None
    project_id: str | None
    organization_id: str | None
    request_timeout_seconds: float
    background_enabled: bool
    default_store: bool
    data_control_mode: Literal[
        "standard",
        "zero_data_retention",
        "strict_no_temporary_provider_state",
    ]
    capability_smoke_test_max_age_days: int
    live_tests_enabled: bool
    daily_budget_usd: Decimal

@dataclass(frozen=True)
class RuntimeSettings:
    environment: Literal["development", "test", "production"]
    debug: bool
    public_base_url: AnyHttpUrl
    timezone: str
    openai: OpenAISettings
```

Django settings remain import-time safe. Provider clients should be initialized lazily or through dependency factories, not during module import.

## 4. Required environment variables

### 4.1 Application

```dotenv
APP_ENV=development
DJANGO_SETTINGS_MODULE=config.settings.development
DJANGO_SECRET_KEY=
DJANGO_SECRET_KEY_FILE=
DJANGO_DEBUG=1
PUBLIC_BASE_URL=http://localhost:8000
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000
TIME_ZONE=Europe/Berlin
DEFAULT_LANGUAGE=en
LOG_LEVEL=INFO
```

Exactly one of `DJANGO_SECRET_KEY` or `DJANGO_SECRET_KEY_FILE` is used. The `_FILE` convention supports Docker/host secret mounts.

### 4.2 PostgreSQL

```dotenv
POSTGRES_DB=ftl_opportunities
POSTGRES_USER=ftl_app
POSTGRES_PASSWORD=
POSTGRES_PASSWORD_FILE=
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
DATABASE_URL=
DATABASE_CONN_MAX_AGE=60
DATABASE_HEALTH_CHECKS=1
```

The application may accept either a complete `DATABASE_URL` or separate values, with one documented precedence rule. Never log a complete connection URL.

### 4.3 Redis and Celery

```dotenv
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=
CELERY_TIMEZONE=Europe/Berlin
CELERY_WORKER_CONCURRENCY=2
CELERY_RESEARCH_WORKER_CONCURRENCY=1
CELERY_TASK_ALWAYS_EAGER=0
CELERY_VISIBILITY_TIMEOUT_SECONDS=14400
```

Large domain output is not stored in a Celery result backend. `CELERY_RESULT_BACKEND` SHOULD remain empty unless a concrete need is documented.

### 4.4 OpenAI

```dotenv
OPENAI_ENABLED=0
OPENAI_API_KEY=
OPENAI_API_KEY_FILE=
OPENAI_WEBHOOK_SECRET=
OPENAI_WEBHOOK_SECRET_FILE=
OPENAI_PROJECT_ID=
OPENAI_ORGANIZATION_ID=
OPENAI_REQUEST_TIMEOUT_SECONDS=120
OPENAI_DAILY_BUDGET_USD=10.00
OPENAI_MONTHLY_BUDGET_USD=200.00
OPENAI_MAX_CONCURRENT_STANDARD_CALLS=4
OPENAI_MAX_CONCURRENT_RESEARCH_CALLS=1
OPENAI_BACKGROUND_ENABLED=1
OPENAI_DEFAULT_STORE=0
OPENAI_DATA_CONTROL_MODE=standard
OPENAI_CAPABILITY_SMOKE_TEST_MAX_AGE_DAYS=30
RUN_LIVE_OPENAI_TESTS=0
LIVE_OPENAI_TEST_BUDGET_USD=1.00
```

`OPENAI_ENABLED=1` requires an API key. The absence of a key with OpenAI disabled is valid.

### 4.5 Model-policy keys

Do not hardcode model IDs in services or prompts.

```dotenv
OPENAI_POLICY_MATERIAL_CHANGE=material_change_default
OPENAI_POLICY_SIGNAL_DETECTOR=signal_detector_default
OPENAI_POLICY_CAPABILITY_CLASSIFIER=capability_classifier_default
OPENAI_POLICY_COMPANY_PATTERN=company_pattern_default
OPENAI_POLICY_RESEARCH_BRIEF=research_brief_default
OPENAI_POLICY_COMPANY_RESEARCH=company_research_default
OPENAI_POLICY_RESEARCH_EXTRACTOR=research_extractor_default
OPENAI_POLICY_DEEP_RESEARCH_BRIEF=deep_research_brief_default
OPENAI_POLICY_DEEP_RESEARCH=deep_research_default
OPENAI_POLICY_DEEP_RESEARCH_EXTRACTOR=deep_research_extractor_default
OPENAI_POLICY_SOLUTION_DESIGNER=solution_designer_default
OPENAI_POLICY_ASSET_MATCHER=asset_matcher_default
OPENAI_POLICY_BUYER_ROLE=buyer_role_default
OPENAI_POLICY_CONTACT_ROUTE=contact_route_default
OPENAI_POLICY_OUTREACH_WRITER=outreach_writer_default
OPENAI_POLICY_EVIDENCE_REVIEWER=evidence_reviewer_default
OPENAI_POLICY_REPLY_CLASSIFIER=reply_classifier_default
```

The referenced policy rows define current model ID/status, reasoning effort, max output/tool/source limits, tool policy, timeouts, background/store/data-control behavior, budget ceiling, and last capability-smoke-test date. `OPENAI_DATA_CONTROL_MODE` supports at least `standard`, `zero_data_retention`, and `strict_no_temporary_provider_state`; the selected policy must be compatible.

### 4.6 Fetching

```dotenv
FETCH_USER_AGENT=FTLOpportunityRadar/1.0 (+https://fasterthanlight.vision/contact)
FETCH_CONNECT_TIMEOUT_SECONDS=10
FETCH_READ_TIMEOUT_SECONDS=30
FETCH_TOTAL_TIMEOUT_SECONDS=60
FETCH_MAX_REDIRECTS=5
FETCH_MAX_RESPONSE_BYTES=10485760
FETCH_PER_DOMAIN_CONCURRENCY=2
FETCH_DEFAULT_REQUESTS_PER_MINUTE=20
FETCH_ALLOW_HTTP=0
PLAYWRIGHT_ENABLED=0
PLAYWRIGHT_MAX_PAGES=2
PLAYWRIGHT_NAVIGATION_TIMEOUT_MS=30000
```

### 4.7 Email/draft integration

```dotenv
EMAIL_INTEGRATION_ENABLED=0
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_DRAFT_PROVIDER=none
EMAIL_FROM_ADDRESS=
AUTOMATIC_FIRST_CONTACT_SEND=0
```

`AUTOMATIC_FIRST_CONTACT_SEND` MUST be hard-disabled by application policy in the initial product, even if an environment value is accidentally set.

### 4.8 Contact-route protection

```dotenv
CONTACT_ROUTE_ENCRYPTION_KEY=
CONTACT_ROUTE_ENCRYPTION_KEY_FILE=
CONTACT_ROUTE_HMAC_KEY=
CONTACT_ROUTE_HMAC_KEY_FILE=
CONTACT_ROUTE_KEY_ID=local-dev-v1
```

Encryption and HMAC use different keys. Production SHOULD provide them through mounted secrets. Rotating a key requires a versioned migration/runbook; never silently change the HMAC key because suppression and deduplication depend on it.

### 4.9 Storage, retention, and backups

```dotenv
MEDIA_ROOT=/app/media
BACKUP_ROOT=/backups
BACKUP_RETENTION_DAYS=30
RAW_SOURCE_RETENTION_DAYS=365
SEARCH_CANDIDATE_RETENTION_DAYS=90
PROVIDER_RESPONSE_RETENTION_DAYS=180
AUDIT_RETENTION_DAYS=2555
BACKUP_ENCRYPTION_ENABLED=1
BACKUP_ENCRYPTION_RECIPIENT=
```

Retention values are policy defaults and require legal/operational review before production.

### 4.9 Observability

```dotenv
OTEL_ENABLED=0
OTEL_EXPORTER_OTLP_ENDPOINT=
SENTRY_DSN=
PROMETHEUS_ENABLED=1
REQUEST_ID_HEADER=X-Request-ID
```

External observability services are optional. Structured local logs and operations records are mandatory.

## 5. Secret loading

Implement one helper:

```python
def read_secret(name: str, *, required: bool = False) -> str | None:
    """Read NAME_FILE first when set, otherwise NAME; strip one trailing newline."""
```

Rules:

- reject simultaneous conflicting direct and file values in production;
- reject world-readable secret files where the platform can inspect permissions;
- never include secret values in validation exceptions;
- represent secrets with redacting types;
- do not pass secrets into Celery arguments;
- rotate keys without changing code;
- use separate development and production API projects/keys.

## 6. Feature flags

Feature flags are typed and visible in operations UI.

```text
openai_enabled
web_search_enabled
deep_research_enabled
playwright_enabled
contact_route_research_enabled
email_draft_integration_enabled
reply_ingestion_enabled
live_provider_tests_enabled
```

Flags gate entry into a stage. Disabling a feature must not make existing records unreadable.

## 7. ModelPolicy

```json
{
  "key": "capability_classifier_default",
  "provider": "openai",
  "model": "configured-current-model-id",
  "model_status": "active",
  "operation": "structured_output",
  "prompt_key": "capability_gap_classifier",
  "prompt_version": "2.1.0",
  "schema_key": "CapabilityAssessmentV2",
  "schema_version": "2.1",
  "reasoning_effort": "low",
  "max_output_tokens": 5000,
  "temperature": null,
  "tool_choice": "none",
  "search_context_size": null,
  "max_tool_calls": null,
  "background": false,
  "store_response": false,
  "data_control_mode": "standard",
  "timeout_seconds": 120,
  "max_attempts": 2,
  "per_call_budget_usd": 0.25,
  "last_capability_smoke_test_at": "2026-08-05T00:00:00Z",
  "active": true
}
```

Policy changes create a new version or audited revision. Historical provider calls retain the exact resolved values.

## 8. Startup validation

Production startup MUST reject:

- `DEBUG=true`;
- placeholder/default Django secret key;
- wildcard host policy;
- HTTP public base URL unless explicitly behind a trusted internal proxy configuration;
- OpenAI enabled without a key;
- enabled model policy with stale/failed capability smoke test;
- background/data-control policy mismatch;
- contact encryption/HMAC key missing when contact storage is enabled;
- deep research enabled without a valid policy and budget;
- automatic first-contact send enabled;
- missing allowed proxy/TLS settings;
- insecure cookie configuration;
- database/Redis URLs with unsupported schemes;
- unparseable retention or budget values.

Development startup should issue clear warnings but must not print secrets.

## 9. Configuration visibility

Operations UI may show:

- feature status;
- active policy keys and versions;
- model names;
- thresholds and budgets;
- schedule state;
- retention values;
- whether credentials are configured.

It must never show API keys, passwords, webhook secrets, complete DSNs, or authorization headers.

## 10. Tests

- direct secret and `_FILE` loading;
- redaction in logs/exceptions;
- production unsafe-setting rejection;
- OpenAI-disabled startup without key;
- OpenAI-enabled startup failure without key;
- model-policy resolution and historical snapshot;
- automatic-send hard block;
- environment precedence;
- `.env.example` completeness check;
- task payloads contain no secret values.

## 11. Acceptance criteria

- one typed settings path is used by web, workers, Beat, and management commands;
- every required variable is documented in `.env.example`;
- production starts only with safe values;
- secrets are absent from logs, task messages, prompts, and HTML;
- model/provider changes require configuration, not service edits;
- the stack can run with all external AI features disabled.
