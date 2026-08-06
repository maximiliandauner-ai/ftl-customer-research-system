from pathlib import Path


def test_env_example_covers_milestone_runtime_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    keys = {
        line.split("=", 1)[0]
        for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    required = {
        "APP_ENV",
        "DJANGO_SETTINGS_MODULE",
        "DJANGO_SECRET_KEY",
        "DJANGO_SECRET_KEY_FILE",
        "PUBLIC_BASE_URL",
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_PASSWORD_FILE",
        "DATABASE_URL",
        "REDIS_URL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "OPENAI_ENABLED",
        "OPENAI_API_KEY",
        "OPENAI_API_KEY_FILE",
        "RUN_LIVE_OPENAI_TESTS",
        "AUTOMATIC_FIRST_CONTACT_SEND",
        "MEDIA_ROOT",
        "BACKUP_ROOT",
    }

    assert required <= keys
