#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
env_file=${ENV_FILE:-.env}
case "$env_file" in
    /*) ;;
    *) env_file="$project_dir/$env_file" ;;
esac

if [ ! -f "$env_file" ]; then
    echo "Environment file not found: $env_file" >&2
    exit 2
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_root=${BACKUP_OUTPUT_ROOT:-$project_dir/backups}
destination="$backup_root/$stamp"
if [ -e "$destination" ]; then
    echo "Refusing to overwrite existing backup: $destination" >&2
    exit 2
fi
mkdir -p "$destination"

compose() {
    ENV_FILE="$env_file" docker compose --project-directory "$project_dir" \
        --env-file "$env_file" -f "$project_dir/compose.yaml" "$@"
}

dump="$destination/database.dump"
artifacts="$destination/artifacts.tar.gz"
compose exec -T postgres sh -lc \
    'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner --no-acl' \
    > "$dump"
test -s "$dump"
compose exec -T postgres pg_restore --list < "$dump" > /dev/null
compose run --rm --no-deps --entrypoint sh web -lc 'tar -czf - -C /app/media .' > "$artifacts"
test -s "$artifacts"

postgres_version=$(compose exec -T postgres postgres --version | tr -d '\r')
migration_count=$(compose exec -T postgres sh -lc \
    'psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --tuples-only --no-align --command="SELECT count(*) FROM django_migrations"' \
    | tr -d '\r')
git_commit=$(git -C "$project_dir" rev-parse HEAD 2>/dev/null || printf 'unknown')

python3 - "$destination/backup_manifest.json" "$stamp" "$postgres_version" "$migration_count" "$git_commit" <<'PY'
import json
import sys
from pathlib import Path

manifest_path, stamp, postgres_version, migration_count, git_commit = sys.argv[1:]
manifest = {
    "schema_version": "2.0",
    "created_at": stamp,
    "status": "complete",
    "backup_type": "full",
    "postgres_version": postgres_version,
    "django_migration_count": int(migration_count),
    "app_git_commit": git_commit,
    "database_file": "database.dump",
    "artifact_file": "artifacts.tar.gz",
}
Path(manifest_path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY

(
    cd "$destination"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum database.dump artifacts.tar.gz backup_manifest.json > SHA256SUMS
    else
        shasum -a 256 database.dump artifacts.tar.gz backup_manifest.json > SHA256SUMS
    fi
)

printf '%s\n' "$destination"
