#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
env_file=${ENV_FILE:-.env}
case "$env_file" in
    /*) ;;
    *) env_file="$project_dir/$env_file" ;;
esac
compose() {
    ENV_FILE="$env_file" docker compose --project-directory "$project_dir" \
        --env-file "$env_file" -f "$project_dir/compose.yaml" -f "$project_dir/compose.dev.yaml" "$@"
}
query='psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --tuples-only --no-align --command="SELECT count(*) FROM django_migrations"'
before=$(compose exec -T postgres sh -lc "$query" | tr -d '\r')
test "$before" -gt 0
compose stop postgres >/dev/null
compose up -d postgres >/dev/null
attempt=0
until compose exec -T postgres sh -lc 'pg_isready --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "PostgreSQL did not become ready after restart." >&2
        exit 1
    fi
    sleep 1
done
after=$(compose exec -T postgres sh -lc "$query" | tr -d '\r')
test "$before" = "$after"
echo "Persistence check passed with $after migration records before and after restart."
