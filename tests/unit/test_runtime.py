from pathlib import Path

import pytest

from config.runtime import (
    ConfigurationError,
    django_database_config,
    load_runtime_settings,
    read_secret,
)


def valid_environment(**overrides: str) -> dict[str, str]:
    values = {
        "APP_ENV": "test",
        "DJANGO_SECRET_KEY": "x" * 48,
        "POSTGRES_DB": "ftl_test",
        "POSTGRES_USER": "ftl_test",
        "POSTGRES_PASSWORD": "database-password",  # pragma: allowlist secret
        "POSTGRES_HOST": "postgres",
        "PUBLIC_BASE_URL": "http://localhost:8000",
        "ALLOWED_HOSTS": "localhost,127.0.0.1",
        "CSRF_TRUSTED_ORIGINS": "http://localhost:8000",
        "USE_SQLITE": "0",
    }
    values.update(overrides)
    return values


def test_openai_disabled_does_not_require_key() -> None:
    runtime = load_runtime_settings(valid_environment(OPENAI_ENABLED="0"))

    assert runtime.openai_api_key is None
    assert runtime.safe_validation_errors() == ()


def test_openai_enabled_without_key_fails_safe_validation() -> None:
    runtime = load_runtime_settings(valid_environment(OPENAI_ENABLED="1"))

    assert runtime.safe_validation_errors() == (
        "OPENAI_ENABLED requires OPENAI_API_KEY or OPENAI_API_KEY_FILE.",
    )


def test_automatic_first_contact_send_is_hard_blocked() -> None:
    runtime = load_runtime_settings(valid_environment(AUTOMATIC_FIRST_CONTACT_SEND="1"))

    assert "AUTOMATIC_FIRST_CONTACT_SEND is prohibited by application policy." in (
        runtime.safe_validation_errors()
    )


def test_production_validation_rejects_unsafe_http_and_hosts() -> None:
    runtime = load_runtime_settings(
        valid_environment(APP_ENV="production", ALLOWED_HOSTS="*", DJANGO_DEBUG="1")
    )

    errors = runtime.safe_validation_errors(deploy=True)

    assert "DJANGO_DEBUG must be disabled in production." in errors
    assert "Production ALLOWED_HOSTS must be explicit and non-empty." in errors
    assert "Production PUBLIC_BASE_URL must use HTTPS." in errors


def test_secret_file_takes_precedence_in_development(tmp_path: Path) -> None:
    secret_file = tmp_path / "secret"
    secret_file.write_text("from-file\n", encoding="utf-8")
    secret_file.chmod(0o600)

    value = read_secret(
        "EXAMPLE",
        environment="development",
        environ={"EXAMPLE": "direct", "EXAMPLE_FILE": str(secret_file)},
    )

    assert value == "from-file"


def test_production_rejects_conflicting_secret_sources(tmp_path: Path) -> None:
    secret_file = tmp_path / "secret"
    secret_file.write_text("from-file", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Set only one of EXAMPLE") as caught:
        read_secret(
            "EXAMPLE",
            environment="production",
            environ={"EXAMPLE": "direct-secret", "EXAMPLE_FILE": str(secret_file)},
        )

    assert "direct-secret" not in str(caught.value)
    assert "from-file" not in str(caught.value)


def test_production_rejects_broad_local_secret_file_permissions(tmp_path: Path) -> None:
    secret_file = tmp_path / "secret"
    secret_file.write_text("sensitive", encoding="utf-8")
    secret_file.chmod(0o644)

    with pytest.raises(ConfigurationError, match="permissions are too broad"):
        read_secret(
            "EXAMPLE",
            environment="production",
            environ={"EXAMPLE_FILE": str(secret_file)},
        )


def test_database_url_precedence_and_redaction() -> None:
    database_url = "postgresql://explicit:secret@db:5432/explicit"  # pragma: allowlist secret
    runtime = load_runtime_settings(valid_environment(DATABASE_URL=database_url))
    database = django_database_config(runtime, Path.cwd())

    assert database["NAME"] == "explicit"
    assert database["HOST"] == "db"
    assert database["PASSWORD"] == "secret"  # pragma: allowlist secret
    assert "secret" not in repr(runtime.database_url)


def test_invalid_boolean_has_safe_error() -> None:
    with pytest.raises(ConfigurationError, match="OPENAI_ENABLED must be a boolean"):
        load_runtime_settings(valid_environment(OPENAI_ENABLED="sometimes"))
