from __future__ import annotations

import os
import stat
from collections.abc import Mapping
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
    deep_research_enabled: bool
    playwright_enabled: bool
    contact_route_research_enabled: bool
    email_draft_integration_enabled: bool
    reply_ingestion_enabled: bool
    live_provider_tests_enabled: bool


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
    automatic_first_contact_send: bool
    use_sqlite: bool
    media_root: Path
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
        if self.features.deep_research_enabled and not self.features.openai_enabled:
            errors.append("DEEP_RESEARCH_ENABLED requires OPENAI_ENABLED.")
        if self.features.web_search_enabled and not self.features.openai_enabled:
            errors.append("WEB_SEARCH_ENABLED requires OPENAI_ENABLED.")
        if self.automatic_first_contact_send:
            errors.append("AUTOMATIC_FIRST_CONTACT_SEND is prohibited by application policy.")
        if self.use_sqlite and self.environment != "test":
            errors.append("USE_SQLITE is allowed only for deterministic tests.")
        if self.celery_worker_concurrency < 1:
            errors.append("CELERY_WORKER_CONCURRENCY must be at least 1.")
        if self.celery_visibility_timeout_seconds < 300:
            errors.append("CELERY_VISIBILITY_TIMEOUT_SECONDS must be at least 300.")
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
            automatic_first_contact_send=_bool("AUTOMATIC_FIRST_CONTACT_SEND", source, False),
            use_sqlite=use_sqlite,
            media_root=Path(_value("MEDIA_ROOT", source, "/app/media")),
            features=FeatureFlags(
                openai_enabled=_bool("OPENAI_ENABLED", source, False),
                web_search_enabled=_bool("WEB_SEARCH_ENABLED", source, False),
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
