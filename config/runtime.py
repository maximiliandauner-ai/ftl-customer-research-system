from __future__ import annotations

import os
import stat
from base64 import urlsafe_b64decode
from binascii import Error as Base64Error
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, cast
from urllib.parse import quote, urlparse

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, SecretStr, ValidationError


class ConfigurationError(RuntimeError):
    """A safe configuration failure that never includes a secret value."""


class FeatureFlags(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    openai_enabled: bool
    web_search_enabled: bool
    standard_research_enabled: bool
    deep_research_enabled: bool
    playwright_enabled: bool
    contact_route_research_enabled: bool
    email_draft_integration_enabled: bool
    reply_ingestion_enabled: bool
    live_provider_tests_enabled: bool


class FetchPolicySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_agent: str
    allow_http: bool
    connect_timeout_seconds: int
    read_timeout_seconds: int
    total_timeout_seconds: int
    max_redirects: int
    max_response_bytes: int
    per_domain_concurrency: int
    default_requests_per_minute: int
    allowed_content_types: tuple[str, ...]
    denied_hostnames: tuple[str, ...]
    denied_cidrs: tuple[str, ...]


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Literal["development", "test", "production"]
    debug: bool
    public_base_url: AnyHttpUrl
    allowed_hosts: tuple[str, ...]
    csrf_trusted_origins: tuple[str, ...]
    timezone: str
    default_language: str
    log_level: str
    django_secret_key: SecretStr
    database_url: SecretStr
    database_conn_max_age: int
    database_health_checks: bool
    redis_url: SecretStr
    celery_broker_url: SecretStr
    celery_timezone: str
    celery_worker_concurrency: int
    celery_task_always_eager: bool
    celery_visibility_timeout_seconds: int
    openai_api_key: SecretStr | None
    contact_route_encryption_key: SecretStr | None = None
    contact_route_hmac_key: SecretStr | None = None
    contact_route_key_id: str = "local-dev-v1"
    openai_daily_budget_usd: Decimal
    openai_monthly_budget_usd: Decimal
    openai_max_concurrent_standard_calls: int
    automatic_first_contact_send: bool
    use_sqlite: bool
    media_root: Path
    fetch: FetchPolicySettings
    features: FeatureFlags

    def safe_validation_errors(self, *, deploy: bool = False) -> tuple[str, ...]:
        errors: list[str] = []
        secret = self.django_secret_key.get_secret_value()
        if len(secret) < 40 or secret.lower().startswith(("change-me", "replace-me")):
            errors.append(
                "DJANGO_SECRET_KEY must be a non-placeholder value of at least 40 characters."
            )
        if self.features.openai_enabled and self.openai_api_key is None:
            errors.append("OPENAI_ENABLED requires OPENAI_API_KEY or OPENAI_API_KEY_FILE.")
        if self.openai_daily_budget_usd <= 0 or self.openai_monthly_budget_usd <= 0:
            errors.append("OpenAI daily and monthly budgets must be positive.")
        if self.openai_monthly_budget_usd < self.openai_daily_budget_usd:
            errors.append("OPENAI_MONTHLY_BUDGET_USD must cover the daily budget.")
        if self.openai_max_concurrent_standard_calls < 1:
            errors.append("OPENAI_MAX_CONCURRENT_STANDARD_CALLS must be at least 1.")
        if self.features.deep_research_enabled and not self.features.openai_enabled:
            errors.append("DEEP_RESEARCH_ENABLED requires OPENAI_ENABLED.")
        if self.features.web_search_enabled and not self.features.openai_enabled:
            errors.append("WEB_SEARCH_ENABLED requires OPENAI_ENABLED.")
        if self.features.standard_research_enabled and not (
            self.features.openai_enabled and self.features.web_search_enabled
        ):
            errors.append(
                "STANDARD_RESEARCH_ENABLED requires OPENAI_ENABLED and WEB_SEARCH_ENABLED."
            )
        contact_keys = (
            self.contact_route_encryption_key,
            self.contact_route_hmac_key,
        )
        if self.features.contact_route_research_enabled and not all(contact_keys):
            errors.append(
                "CONTACT_ROUTE_RESEARCH_ENABLED requires separate encryption and HMAC keys."
            )
        if self.contact_route_encryption_key and not _valid_32_byte_key(
            self.contact_route_encryption_key.get_secret_value()
        ):
            errors.append("CONTACT_ROUTE_ENCRYPTION_KEY must encode exactly 32 random bytes.")
        if self.contact_route_hmac_key and not _valid_32_byte_key(
            self.contact_route_hmac_key.get_secret_value()
        ):
            errors.append("CONTACT_ROUTE_HMAC_KEY must encode exactly 32 random bytes.")
        if not self.contact_route_key_id or len(self.contact_route_key_id) > 64:
            errors.append("CONTACT_ROUTE_KEY_ID must be between 1 and 64 characters.")
        if self.automatic_first_contact_send:
            errors.append("AUTOMATIC_FIRST_CONTACT_SEND is prohibited by application policy.")
        if self.use_sqlite and self.environment != "test":
            errors.append("USE_SQLITE is allowed only for deterministic tests.")
        if self.celery_worker_concurrency < 1:
            errors.append("CELERY_WORKER_CONCURRENCY must be at least 1.")
        if self.celery_visibility_timeout_seconds < 300:
            errors.append("CELERY_VISIBILITY_TIMEOUT_SECONDS must be at least 300.")
        if not 1 <= self.fetch.connect_timeout_seconds <= 60:
            errors.append("FETCH_CONNECT_TIMEOUT_SECONDS must be between 1 and 60.")
        if not 1 <= self.fetch.read_timeout_seconds <= 120:
            errors.append("FETCH_READ_TIMEOUT_SECONDS must be between 1 and 120.")
        if self.fetch.total_timeout_seconds < self.fetch.connect_timeout_seconds:
            errors.append("FETCH_TOTAL_TIMEOUT_SECONDS must cover the connect timeout.")
        if not 0 <= self.fetch.max_redirects <= 10:
            errors.append("FETCH_MAX_REDIRECTS must be between 0 and 10.")
        if not 1024 <= self.fetch.max_response_bytes <= 52_428_800:
            errors.append("FETCH_MAX_RESPONSE_BYTES must be between 1 KiB and 50 MiB.")
        if self.fetch.per_domain_concurrency < 1:
            errors.append("FETCH_PER_DOMAIN_CONCURRENCY must be at least 1.")
        if self.fetch.default_requests_per_minute < 1:
            errors.append("FETCH_DEFAULT_REQUESTS_PER_MINUTE must be at least 1.")
        if not self.fetch.allowed_content_types:
            errors.append("FETCH_ALLOWED_CONTENT_TYPES must not be empty.")
        if self.timezone != "Europe/Berlin" or self.celery_timezone != "Europe/Berlin":
            errors.append("Application and Celery business timezone must be Europe/Berlin.")
        broker_scheme = urlparse(self.celery_broker_url.get_secret_value()).scheme
        if broker_scheme not in {"redis", "rediss"}:
            errors.append("CELERY_BROKER_URL must use redis:// or rediss:// for this release.")
        database_scheme = urlparse(self.database_url.get_secret_value()).scheme
        if not self.use_sqlite and database_scheme not in {"postgres", "postgresql"}:
            errors.append("DATABASE_URL must use postgres:// or postgresql://.")
        if deploy or self.environment == "production":
            if self.debug:
                errors.append("DJANGO_DEBUG must be disabled in production.")
            if "*" in self.allowed_hosts or not self.allowed_hosts:
                errors.append("Production ALLOWED_HOSTS must be explicit and non-empty.")
            if self.public_base_url.scheme != "https":
                errors.append("Production PUBLIC_BASE_URL must use HTTPS.")
            if not self.csrf_trusted_origins or any(
                not origin.startswith("https://") for origin in self.csrf_trusted_origins
            ):
                errors.append("Production CSRF_TRUSTED_ORIGINS must contain HTTPS origins only.")
        return tuple(errors)


def _value(name: str, environ: Mapping[str, str], default: str = "") -> str:
    return environ.get(name, default).strip()


def _valid_32_byte_key(value: str) -> bool:
    try:
        decoded = urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (Base64Error, ValueError):
        return False
    return len(decoded) == 32


def _bool(name: str, environ: Mapping[str, str], default: bool = False) -> bool:
    raw = _value(name, environ)
    if not raw:
        return default
    if raw.lower() in {"1", "true", "yes", "on"}:
        return True
    if raw.lower() in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value.")


def _integer(name: str, environ: Mapping[str, str], default: int) -> int:
    raw = _value(name, environ)
    try:
        return int(raw) if raw else default
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc


def _decimal(name: str, environ: Mapping[str, str], default: str) -> Decimal:
    raw = _value(name, environ, default)
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ConfigurationError(f"{name} must be a decimal value.") from exc


def _csv(name: str, environ: Mapping[str, str], default: str = "") -> tuple[str, ...]:
    raw = _value(name, environ, default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _strip_one_trailing_newline(value: str) -> str:
    if value.endswith("\r\n"):
        return value[:-2]
    if value.endswith("\n"):
        return value[:-1]
    return value


def read_secret(
    name: str,
    *,
    required: bool = False,
    environment: str = "development",
    environ: Mapping[str, str] | None = None,
) -> str | None:
    source = os.environ if environ is None else environ
    direct = source.get(name, "")
    file_name = source.get(f"{name}_FILE", "").strip()
    if direct and file_name and environment == "production":
        raise ConfigurationError(f"Set only one of {name} and {name}_FILE in production.")
    value = direct or None
    if file_name:
        path = Path(file_name)
        try:
            mode = path.stat().st_mode
            if (
                environment == "production"
                and not path.is_relative_to("/run/secrets")
                and mode & (stat.S_IRGRP | stat.S_IROTH)
            ):
                raise ConfigurationError(f"{name}_FILE permissions are too broad.")
            value = _strip_one_trailing_newline(path.read_text(encoding="utf-8"))
        except ConfigurationError:
            raise
        except OSError as exc:
            raise ConfigurationError(f"Unable to read {name}_FILE.") from exc
    if required and not value:
        raise ConfigurationError(f"{name} or {name}_FILE is required.")
    return value


def _database_url(environ: Mapping[str, str], environment: str) -> str:
    explicit = _value("DATABASE_URL", environ)
    if explicit:
        return explicit
    password = read_secret(
        "POSTGRES_PASSWORD", required=True, environment=environment, environ=environ
    )
    user = quote(_value("POSTGRES_USER", environ, "ftl_app"), safe="")
    encoded_password = quote(password or "", safe="")
    host = _value("POSTGRES_HOST", environ, "postgres")
    port = _integer("POSTGRES_PORT", environ, 5432)
    database = quote(_value("POSTGRES_DB", environ, "ftl_opportunities"), safe="")
    return f"postgresql://{user}:{encoded_password}@{host}:{port}/{database}"


def load_runtime_settings(environ: Mapping[str, str] | None = None) -> RuntimeSettings:
    source = os.environ if environ is None else environ
    environment = cast(
        Literal["development", "test", "production"],
        _value("APP_ENV", source, "development"),
    )
    use_sqlite = _bool("USE_SQLITE", source, False)
    secret = read_secret(
        "DJANGO_SECRET_KEY", required=True, environment=environment, environ=source
    )
    openai_api_key = read_secret(
        "OPENAI_API_KEY", required=False, environment=environment, environ=source
    )
    contact_encryption_key = read_secret(
        "CONTACT_ROUTE_ENCRYPTION_KEY",
        required=False,
        environment=environment,
        environ=source,
    )
    contact_hmac_key = read_secret(
        "CONTACT_ROUTE_HMAC_KEY",
        required=False,
        environment=environment,
        environ=source,
    )
    try:
        return RuntimeSettings(
            environment=environment,
            debug=_bool("DJANGO_DEBUG", source, environment == "development"),
            public_base_url=AnyHttpUrl(_value("PUBLIC_BASE_URL", source, "http://localhost:8000")),
            allowed_hosts=_csv("ALLOWED_HOSTS", source, "localhost,127.0.0.1"),
            csrf_trusted_origins=_csv("CSRF_TRUSTED_ORIGINS", source, "http://localhost:8000"),
            timezone=_value("TIME_ZONE", source, "Europe/Berlin"),
            default_language=_value("DEFAULT_LANGUAGE", source, "en"),
            log_level=_value("LOG_LEVEL", source, "INFO").upper(),
            django_secret_key=SecretStr(secret or ""),
            database_url=SecretStr(
                "sqlite://" if use_sqlite else _database_url(source, environment)
            ),
            database_conn_max_age=_integer("DATABASE_CONN_MAX_AGE", source, 60),
            database_health_checks=_bool("DATABASE_HEALTH_CHECKS", source, True),
            redis_url=SecretStr(_value("REDIS_URL", source, "redis://redis:6379/0")),
            celery_broker_url=SecretStr(
                _value("CELERY_BROKER_URL", source, "redis://redis:6379/1")
            ),
            celery_timezone=_value("CELERY_TIMEZONE", source, "Europe/Berlin"),
            celery_worker_concurrency=_integer("CELERY_WORKER_CONCURRENCY", source, 2),
            celery_task_always_eager=_bool("CELERY_TASK_ALWAYS_EAGER", source, False),
            celery_visibility_timeout_seconds=_integer(
                "CELERY_VISIBILITY_TIMEOUT_SECONDS", source, 14400
            ),
            openai_api_key=SecretStr(openai_api_key) if openai_api_key else None,
            contact_route_encryption_key=(
                SecretStr(contact_encryption_key) if contact_encryption_key else None
            ),
            contact_route_hmac_key=SecretStr(contact_hmac_key) if contact_hmac_key else None,
            contact_route_key_id=_value("CONTACT_ROUTE_KEY_ID", source, "local-dev-v1"),
            openai_daily_budget_usd=_decimal(
                "OPENAI_DAILY_BUDGET_USD",
                source,
                "10.00",
            ),
            openai_monthly_budget_usd=_decimal(
                "OPENAI_MONTHLY_BUDGET_USD",
                source,
                "200.00",
            ),
            openai_max_concurrent_standard_calls=_integer(
                "OPENAI_MAX_CONCURRENT_STANDARD_CALLS",
                source,
                4,
            ),
            automatic_first_contact_send=_bool("AUTOMATIC_FIRST_CONTACT_SEND", source, False),
            use_sqlite=use_sqlite,
            media_root=Path(_value("MEDIA_ROOT", source, "/app/media")),
            fetch=FetchPolicySettings(
                user_agent=_value(
                    "FETCH_USER_AGENT",
                    source,
                    "FTLOpportunityRadar/1.0 (+https://fasterthanlight.vision/contact)",
                ),
                allow_http=_bool("FETCH_ALLOW_HTTP", source, False),
                connect_timeout_seconds=_integer("FETCH_CONNECT_TIMEOUT_SECONDS", source, 10),
                read_timeout_seconds=_integer("FETCH_READ_TIMEOUT_SECONDS", source, 30),
                total_timeout_seconds=_integer("FETCH_TOTAL_TIMEOUT_SECONDS", source, 60),
                max_redirects=_integer("FETCH_MAX_REDIRECTS", source, 5),
                max_response_bytes=_integer("FETCH_MAX_RESPONSE_BYTES", source, 10_485_760),
                per_domain_concurrency=_integer("FETCH_PER_DOMAIN_CONCURRENCY", source, 2),
                default_requests_per_minute=_integer(
                    "FETCH_DEFAULT_REQUESTS_PER_MINUTE", source, 20
                ),
                allowed_content_types=_csv(
                    "FETCH_ALLOWED_CONTENT_TYPES",
                    source,
                    "text/html,application/xhtml+xml,application/json,application/ld+json,"
                    "text/plain,application/xml,text/xml,application/rss+xml",
                ),
                denied_hostnames=_csv(
                    "FETCH_DENY_HOSTNAMES",
                    source,
                    "localhost,postgres,redis,web,worker-core,worker-research,beat,proxy,"
                    "host.docker.internal,gateway.docker.internal,metadata.google.internal",
                ),
                denied_cidrs=_csv("FETCH_DENY_CIDRS", source),
            ),
            features=FeatureFlags(
                openai_enabled=_bool("OPENAI_ENABLED", source, False),
                web_search_enabled=_bool("WEB_SEARCH_ENABLED", source, False),
                standard_research_enabled=_bool("STANDARD_RESEARCH_ENABLED", source, False),
                deep_research_enabled=_bool("DEEP_RESEARCH_ENABLED", source, False),
                playwright_enabled=_bool("PLAYWRIGHT_ENABLED", source, False),
                contact_route_research_enabled=_bool(
                    "CONTACT_ROUTE_RESEARCH_ENABLED", source, False
                ),
                email_draft_integration_enabled=_bool("EMAIL_INTEGRATION_ENABLED", source, False),
                reply_ingestion_enabled=_bool("REPLY_INGESTION_ENABLED", source, False),
                live_provider_tests_enabled=_bool("RUN_LIVE_OPENAI_TESTS", source, False),
            ),
        )
    except ValidationError as exc:
        field_names = sorted(
            {".".join(str(part) for part in error["loc"]) for error in exc.errors()}
        )
        raise ConfigurationError(
            f"Invalid runtime configuration fields: {', '.join(field_names)}."
        ) from exc


def django_database_config(runtime: RuntimeSettings, base_dir: Path) -> dict[str, object]:
    if runtime.use_sqlite:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": base_dir / "test.sqlite3",
        }
    parsed = urlparse(runtime.database_url.get_secret_value())
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": parsed.port or 5432,
        "CONN_MAX_AGE": runtime.database_conn_max_age,
        "CONN_HEALTH_CHECKS": runtime.database_health_checks,
    }
