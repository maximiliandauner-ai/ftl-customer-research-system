# 04 — Docker Local Development and Server Parity

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Platform and DevOps  
**Audience:** Codex and FTL engineers

## 1. Purpose

Specify a reproducible Docker environment that runs locally on a laptop, preserves data, supports deterministic tests, and transfers to a future server without rewriting application code.

## 2. Baseline

The repository SHOULD use:

```text
Python 3.13
Django >=5.2.17,<5.3
Celery >=5.6.3,<5.7
PostgreSQL 18.4+
Redis >=8.10.0,<9
Docker Compose Specification
```

Exact Python packages belong in `pyproject.toml` and a committed lock file. Docker images MUST be pinned to reviewed patch tags and SHOULD be pinned to digests for production.

## 3. Required files

```text
Dockerfile
compose.yaml
compose.dev.yaml
compose.prod.yaml
.dockerignore
.env.example
scripts/
  start-web.sh
  start-worker.sh
  start-beat.sh
  wait-for-db.py
  backup-postgres.sh
  restore-postgres.sh
Makefile
```

Do not use the deprecated top-level Compose `version` key.

## 4. Application image

Use a multi-stage Dockerfile.

### Builder stage

- install the locked Python environment;
- compile wheels where needed;
- build Tailwind/static assets when the repository owns that build;
- run without embedding `.env` or secrets.

### Runtime stage

- minimal supported Python image;
- non-root `app` user with fixed UID/GID where practical;
- copy only runtime dependencies and application files;
- set `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`;
- include a process init through Compose `init: true` rather than installing an unnecessary supervisor;
- write only to declared media/tmp paths;
- define no secret as an image `ARG` or `ENV` value.

The same application image is used by web, workers, Beat, migration jobs, and management commands.

## 5. Compose service topology

The normative shape is:

```yaml
name: ftl-opportunity-intelligence

x-app-common: &app-common
  build:
    context: .
    target: runtime
  env_file:
    - .env
  init: true
  restart: unless-stopped
  networks:
    - backend
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy

services:
  postgres:
    image: postgres:18.4-alpine
    env_file:
      - .env
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 30
      start_period: 10s
    volumes:
      - postgres_data:/var/lib/postgresql
    networks:
      - backend
    restart: unless-stopped

  redis:
    image: redis:8.10.0-alpine
    command:
      - redis-server
      - --appendonly
      - "yes"
      - --appendfsync
      - everysec
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 30
      start_period: 5s
    volumes:
      - redis_data:/data
    networks:
      - backend
    restart: unless-stopped

  migrate:
    <<: *app-common
    command: ["python", "manage.py", "migrate", "--noinput"]
    restart: "no"

  web:
    <<: *app-common
    command: ["./scripts/start-web.sh"]
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    volumes:
      - media_data:/app/media
    expose:
      - "8000"

  worker-core:
    <<: *app-common
    command:
      - ./scripts/start-worker.sh
      - discovery,fetch,parse,classification,aggregation,solution_design,asset_matching,drafting,maintenance
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    volumes:
      - media_data:/app/media

  worker-research:
    <<: *app-common
    command:
      - ./scripts/start-worker.sh
      - research,deep_research,contact_enrichment
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    volumes:
      - media_data:/app/media

  beat:
    <<: *app-common
    command: ["./scripts/start-beat.sh"]
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully

  proxy:
    image: caddy:2-alpine
    depends_on:
      web:
        condition: service_started
    ports:
      - "127.0.0.1:${WEB_PORT:-8000}:80"
    volumes:
      - ./docker/Caddyfile.dev:/etc/caddy/Caddyfile:ro
    networks:
      - backend

networks:
  backend:

volumes:
  postgres_data:
  redis_data:
  media_data:
```

The image examples are a reviewed baseline, not permission to ignore newer security patches. When changing them, update `31_TECHNICAL_REFERENCES.md`, run the full test suite, and pin production digests.

For PostgreSQL 18+, mount the official image volume at `/var/lib/postgresql`. Do not mount only `/var/lib/postgresql/data`; the image now uses version-specific `PGDATA` beneath the parent volume.

## 6. Migration service

Migrations MUST run as a one-shot service before web/workers start.

Do not:

- run migrations concurrently from every web/worker startup;
- create migrations automatically during startup;
- hide migration errors by continuing;
- allow workers to process tasks against an outdated schema.

Production deployment runs the migration job once per release before replacing application containers.

## 7. Development override

`compose.dev.yaml` MAY:

- bind-mount the source tree;
- expose PostgreSQL and Redis on loopback only for local tools;
- enable Django debug toolbar;
- use Django’s development server;
- add Mailpit or a local email backend;
- enable auto-reload;
- mount test fixtures.

Example:

```yaml
services:
  web:
    volumes:
      - .:/app
      - media_data:/app/media
    ports:
      - "127.0.0.1:${DJANGO_DEV_PORT:-8001}:8000"
  worker-core:
    volumes:
      - .:/app
      - media_data:/app/media
  postgres:
    ports:
      - "127.0.0.1:${POSTGRES_PORT:-5432}:5432"
  redis:
    ports:
      - "127.0.0.1:${REDIS_PORT:-6379}:6379"
```

The proxy remains available at `${WEB_PORT:-8000}` while the optional direct Django development server uses `${DJANGO_DEV_PORT:-8001}`; the two mappings MUST NOT share a host port. Dev-only mounts and debug behavior MUST NOT appear in `compose.prod.yaml`.

## 8. Production override

`compose.prod.yaml` MUST:

- use a prebuilt immutable image tag/digest;
- disable source bind mounts;
- disable debug;
- not publish PostgreSQL or Redis ports;
- configure secure proxy headers and TLS;
- set resource limits appropriate to the server;
- use `read_only: true` where the service does not require filesystem writes;
- mount `tmpfs` for `/tmp` where compatible;
- use `cap_drop: [ALL]` and `security_opt: ["no-new-privileges:true"]` where compatible;
- use encrypted backup storage;
- use restart policies and log rotation;
- separate database credentials from application settings;
- restrict network access where operationally possible.

Do not hardcode production domains, secrets, or server paths into application code.

## 9. Playwright isolation

Browser rendering is optional and runs in a separate profile/service.

```text
profile: browser
queue: browser_fetch
separate image with pinned browser dependencies
no persistent browser profile
no downloads
no arbitrary file access
bounded CPU, memory, navigation time, and response size
```

The core stack MUST work without starting the Playwright service. Items requiring it enter a visible `browser_required` state.

## 10. Startup scripts

### `start-web.sh`

- fail on unset critical settings;
- run Django deployment/system checks appropriate to the environment;
- collect static assets in production when required;
- start the configured WSGI/ASGI server;
- never run migrations itself.

### `start-worker.sh`

- accept an explicit queue list;
- set concurrency through environment;
- use worker shutdown settings from `24_CELERY_ORCHESTRATION_AND_SCHEDULING.md`;
- fail if database schema is not current;
- not print secrets.

### `start-beat.sh`

- start one Beat scheduler only;
- use the database scheduler;
- validate timezone `Europe/Berlin` for business schedules while storing UTC timestamps.

## 11. Required Makefile interface

At minimum:

```text
make bootstrap          # create local env file only when absent; build images
make up                 # start development stack
make down               # stop without deleting data
make destroy            # explicit confirmation before deleting volumes
make logs
make shell
make django-shell
make migrate
make makemigrations
make check-migrations
make format
make lint
make typecheck
make test
make test-integration
make test-e2e
make compose-config
make check-docs
make backup
make restore FILE=...
make verify
```

`make destroy` must be visibly destructive and require an explicit opt-in variable or confirmation.

## 12. Health behavior

- `/health/live`: process is running; no expensive dependency check.
- `/health/ready`: database reachable, migrations current, critical settings valid, and application can serve requests.
- worker health: operations heartbeat plus Celery inspect only as diagnostic.
- Redis failure may make async work unavailable but must not corrupt existing dashboard data.

## 13. Apple Silicon and architecture compatibility

Local development must work on modern macOS ARM64 and Linux AMD64. Dependencies and Docker images must be multi-architecture or the limitation must be documented. Do not force `linux/amd64` globally unless a specific optional browser dependency requires it.

## 14. Acceptance tests

1. Clean checkout plus `.env` starts with one documented command.
2. Web, PostgreSQL, Redis, worker, and Beat reach healthy states.
3. Migration service completes before application services.
4. Database records survive `docker compose down` and container recreation.
5. `docker compose config` succeeds for base+dev and base+prod.
6. Application containers run as non-root.
7. Production config has no source mount or public DB/Redis port.
8. The stack runs with AI disabled and no `OPENAI_API_KEY`.
9. Tests execute inside containers.
10. Backup/restore is demonstrated against a clean volume.
