SHELL := /bin/sh

ENV_FILE ?= $(if $(wildcard .env),.env,.env.example)
BASE_COMPOSE = ENV_FILE=$(ENV_FILE) docker compose --env-file $(ENV_FILE) -f compose.yaml
DEV_COMPOSE = $(BASE_COMPOSE) -f compose.dev.yaml
QUALITY_RUN = $(DEV_COMPOSE) --profile quality run --rm --no-deps --build quality

.PHONY: backup bootstrap bootstrap-contact-keys bootstrap-data check-deploy check-docs check-migrations compose-config destroy \
	down django-shell format lint logs makemigrations migrate persistence-check restore \
	restore-drill secret-scan shell test test-e2e test-integration typecheck up verify

bootstrap:
	python3 scripts/bootstrap_env.py
	ENV_FILE=.env docker compose --env-file .env -f compose.yaml -f compose.dev.yaml build

bootstrap-contact-keys:
	python3 scripts/bootstrap_env.py --fill-missing-contact-keys

up:
	@test -f .env || (echo "Run 'make bootstrap' first." >&2; exit 1)
	@ENV_FILE=.env docker compose --env-file .env -f compose.yaml -f compose.dev.yaml up -d postgres redis
	@ENV_FILE=.env docker compose --env-file .env -f compose.yaml -f compose.dev.yaml --profile release run --rm migrate
	@ENV_FILE=.env docker compose --env-file .env -f compose.yaml -f compose.dev.yaml run --rm web python manage.py bootstrap_ftl_platform
	@ENV_FILE=.env docker compose --env-file .env -f compose.yaml -f compose.dev.yaml --profile workers up -d web worker-core worker-research beat proxy

bootstrap-data:
	$(DEV_COMPOSE) run --rm web python manage.py bootstrap_ftl_platform

down:
	$(DEV_COMPOSE) --profile workers down

destroy:
	@test "$(CONFIRM_DESTROY)" = "ftl-local-data" || (echo "Refusing to delete volumes. Re-run with CONFIRM_DESTROY=ftl-local-data." >&2; exit 2)
	$(DEV_COMPOSE) --profile workers down --volumes

logs:
	$(DEV_COMPOSE) --profile workers logs -f --tail=200

shell:
	$(DEV_COMPOSE) run --rm web /bin/sh

django-shell:
	$(DEV_COMPOSE) run --rm web python manage.py shell

migrate:
	$(DEV_COMPOSE) --profile release run --rm migrate

makemigrations:
	$(DEV_COMPOSE) run --rm web python manage.py makemigrations

check-migrations:
	$(QUALITY_RUN) python manage.py makemigrations --check --dry-run

format:
	$(QUALITY_RUN) ruff format .
	$(QUALITY_RUN) ruff check --fix .

lint:
	$(QUALITY_RUN) ruff format --check .
	$(QUALITY_RUN) ruff check .

typecheck:
	$(QUALITY_RUN) mypy config apps domain

check-deploy:
	$(QUALITY_RUN) sh -c 'APP_ENV=production DJANGO_SETTINGS_MODULE=config.settings.production DJANGO_DEBUG=0 DJANGO_SECRET_KEY=ci-only-deployment-check-key-with-more-than-fifty-characters PUBLIC_BASE_URL=https://opportunities.example.invalid ALLOWED_HOSTS=opportunities.example.invalid CSRF_TRUSTED_ORIGINS=https://opportunities.example.invalid POSTGRES_PASSWORD=ci-placeholder-not-used USE_SQLITE=0 python manage.py check --deploy'

test:
	$(QUALITY_RUN) pytest -m "not integration and not e2e and not live_provider" --cov --cov-report=term-missing

test-integration:
	@test -f .env || (echo "Run 'make bootstrap' first." >&2; exit 1)
	@ENV_FILE=.env docker compose --env-file .env -f compose.yaml up -d postgres
	@ENV_FILE=.env docker compose --env-file .env -f compose.yaml --profile quality run --rm --no-deps -e USE_SQLITE=0 quality pytest -m integration

test-e2e:
	$(QUALITY_RUN) pytest -m e2e

compose-config:
	ENV_FILE=.env.example docker compose --env-file .env.example -f compose.yaml --profile '*' config --format json > /tmp/ftl-compose-base.json
	ENV_FILE=.env.example docker compose --env-file .env.example -f compose.yaml -f compose.dev.yaml --profile '*' config --format json > /tmp/ftl-compose-dev.json
	ENV_FILE=.env.example APP_IMAGE=ftl-opportunity-intelligence:milestone1 PUBLIC_DOMAIN=opportunities.example.invalid docker compose --env-file .env.example -f compose.yaml -f compose.prod.yaml --profile '*' config --format json > /tmp/ftl-compose-prod.json
	python3 scripts/check_compose_policy.py /tmp/ftl-compose-base.json /tmp/ftl-compose-dev.json /tmp/ftl-compose-prod.json

check-docs:
	$(QUALITY_RUN) python scripts/check_docs.py

secret-scan:
	$(QUALITY_RUN) sh -c 'detect-secrets scan --all-files --exclude-files "(^|/)([.]env($$|[.])|backups/|uv.lock|docs/ftl-opportunity-intelligence/|[.](git|mypy_cache|pytest_cache|ruff_cache)/)" | python scripts/assert_no_secrets.py'

backup:
	@test -f .env || (echo "Run 'make bootstrap' first." >&2; exit 1)
	ENV_FILE=.env ./scripts/backup-postgres.sh

restore:
	@test -n "$(FILE)" || (echo "Set FILE=backups/<timestamp>/database.dump" >&2; exit 2)
	@test -n "$(TARGET_DATABASE)" || (echo "Set TARGET_DATABASE to a new database name" >&2; exit 2)
	ENV_FILE=$(ENV_FILE) TARGET_DATABASE=$(TARGET_DATABASE) ./scripts/restore-postgres.sh "$(FILE)"

restore-drill:
	@test -n "$(FILE)" || (echo "Set FILE=backups/<timestamp>/database.dump" >&2; exit 2)
	./scripts/restore-drill.sh "$(FILE)"

persistence-check:
	@test -f .env || (echo "Run 'make bootstrap' first." >&2; exit 1)
	ENV_FILE=.env ./scripts/check-persistence.sh

verify: lint typecheck check-migrations check-deploy test test-integration test-e2e compose-config check-docs secret-scan
