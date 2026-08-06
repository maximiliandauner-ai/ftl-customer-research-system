from pathlib import Path

from csp.constants import NONE, SELF
from kombu import Exchange, Queue

from config.runtime import django_database_config, load_runtime_settings
from domain.queues import QUEUE_POLICY

BASE_DIR = Path(__file__).resolve().parents[2]
RUNTIME_SETTINGS = load_runtime_settings()

SECRET_KEY = RUNTIME_SETTINGS.django_secret_key.get_secret_value()
DEBUG = RUNTIME_SETTINGS.debug
ALLOWED_HOSTS = list(RUNTIME_SETTINGS.allowed_hosts)
CSRF_TRUSTED_ORIGINS = list(RUNTIME_SETTINGS.csrf_trusted_origins)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "csp",
    "django_celery_beat",
    "apps.accounts.apps.AccountsConfig",
    "apps.companies.apps.CompaniesConfig",
    "apps.contacts.apps.ContactsConfig",
    "apps.core.apps.CoreConfig",
    "apps.discovery.apps.DiscoveryConfig",
    "apps.jobs.apps.JobsConfig",
    "apps.knowledge.apps.KnowledgeConfig",
    "apps.operations.apps.OperationsConfig",
    "apps.opportunities.apps.OpportunitiesConfig",
    "apps.providers.apps.ProvidersConfig",
    "apps.research.apps.ResearchConfig",
    "apps.signals.apps.SignalsConfig",
    "apps.solutions.apps.SolutionsConfig",
    "apps.sources.apps.SourcesConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
    "apps.core.middleware.RequestCorrelationMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": django_database_config(RUNTIME_SETTINGS, BASE_DIR)}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

LANGUAGE_CODE = RUNTIME_SETTINGS.default_language
TIME_ZONE = RUNTIME_SETTINGS.timezone
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = RUNTIME_SETTINGS.media_root
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "overview"
LOGOUT_REDIRECT_URL = "login"

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "base-uri": [NONE],
        "connect-src": [SELF],
        "font-src": [SELF],
        "form-action": [SELF],
        "frame-ancestors": [NONE],
        "img-src": [SELF, "data:"],
        "object-src": [NONE],
        "script-src": [NONE],
        "style-src": [SELF],
    }
}

CELERY_BROKER_URL = RUNTIME_SETTINGS.celery_broker_url.get_secret_value()
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_ALWAYS_EAGER = RUNTIME_SETTINGS.celery_task_always_eager
CELERY_TIMEZONE = RUNTIME_SETTINGS.celery_timezone
CELERY_ENABLE_UTC = True
CELERY_WORKER_CONCURRENCY = RUNTIME_SETTINGS.celery_worker_concurrency
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": RUNTIME_SETTINGS.celery_visibility_timeout_seconds
}
CELERY_TASK_DEFAULT_QUEUE = "maintenance"
CELERY_TASK_QUEUES = tuple(
    Queue(
        name,
        Exchange(QUEUE_POLICY.exchange_name(name), type="direct"),
        routing_key=name,
    )
    for name in QUEUE_POLICY.names
)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.core.logging.SafeJsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {
        "handlers": ["console"],
        "level": RUNTIME_SETTINGS.log_level,
    },
}
