# FTL Opportunity Intelligence & Outreach Platform

Local-first opportunity intelligence for Faster Than Light. The audited implementation specification lives in [`docs/ftl-opportunity-intelligence/`](docs/ftl-opportunity-intelligence/README.md), and the current software checkpoint is recorded in [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md).

## License

This project is source-available under the PolyForm Noncommercial License 1.0.0.

Commercial use, commercial deployment, integration into commercial products or services, and use for commercial purposes require a separate written licence from Faster Than Light.

For commercial licensing enquiries, contact: maximilian.dauner@ftl.vision

## Milestone 1 quick start

Requirements: Docker Engine with Compose v2. The runtime and all quality checks use Docker; the host-only bootstrap helper uses Python solely to generate local development secrets.

```sh
make bootstrap
make up
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

`make bootstrap` creates `.env` only when absent, gives it restrictive permissions, and builds the reviewed images. `make up` starts PostgreSQL and Redis, runs migrations once through the explicit release service, then starts web, workers, Beat, and the proxy. PostgreSQL and Redis are private in the base stack; the development override exposes them on loopback only.

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) after creating an operator and assigning one canonical FTL role:

```sh
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web python manage.py createsuperuser
docker compose --env-file .env -f compose.yaml -f compose.dev.yaml exec web \
  python manage.py assign_team_role <username> founder --reason initial_local_access
```

The authenticated workspace exposes overview, pipeline-run, outbox, and append-only audit pages. Founders and administrators may create a durable integrity checkpoint. The database transaction creates the run, audit event, and outbox command; Beat dispatches it through Celery, and the idempotent consumer records one durable completion step. Detailed dependency health is permissioned at `/health/dependencies`; public liveness and readiness reveal only bounded status.

Stop without deleting data:

```sh
make down
```

The destructive `make destroy` target is guarded and is never part of normal development or verification.

## Quality interface

```sh
make format
make lint
make typecheck
make check-migrations
make check-deploy
make test
make test-integration
make test-e2e
make compose-config
make check-docs
make secret-scan
make verify
```

Quality commands run in the Docker `quality` image. Deterministic tests use fixtures and local services only. Live OpenAI calls are disabled, require explicit future implementation and policy activation, and are not performed by any milestone 1 command.

## Database operations

```sh
make migrate
make backup
make restore-drill FILE=backups/<timestamp>/database.dump
```

Backups include a PostgreSQL custom-format dump, the local media volume archive, a manifest, and SHA-256 checksums. `restore-drill` restores into an isolated temporary PostgreSQL 18 container and never touches the canonical database. Direct restore into the development PostgreSQL service requires a new database name and refuses an existing target.

## Compose layouts

- `compose.yaml`: private data services and the shared application topology.
- `compose.dev.yaml`: source mounts and loopback-only developer ports.
- `compose.prod.yaml`: immutable prebuilt image, TLS proxy, read-only app roots, dropped capabilities, and no public database/broker ports.

Production startup requires real secrets, HTTPS hosts/origins, and an immutable `APP_IMAGE` tag or digest. See [`.env.example`](.env.example) and [`docs/ftl-opportunity-intelligence/05_CONFIGURATION_AND_SECRETS.md`](docs/ftl-opportunity-intelligence/05_CONFIGURATION_AND_SECRETS.md).
