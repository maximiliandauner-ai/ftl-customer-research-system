#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: TARGET_DATABASE=new_database restore-postgres.sh FILE" >&2
    exit 2
fi
dump=$1
target=${TARGET_DATABASE:-}
case "$target" in
    ""|*[!A-Za-z0-9_]*)
        echo "TARGET_DATABASE must contain only letters, numbers, and underscores." >&2
        exit 2
        ;;
esac
test -s "$dump" || { echo "Backup dump is missing or empty: $dump" >&2; exit 2; }

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
env_file=${ENV_FILE:-.env}
case "$env_file" in
    /*) ;;
    *) env_file="$project_dir/$env_file" ;;
esac
compose() {
    ENV_FILE="$env_file" docker compose --project-directory "$project_dir" \
        --env-file "$env_file" -f "$project_dir/compose.yaml" "$@"
}

canonical=$(compose exec -T postgres printenv POSTGRES_DB | tr -d '\r')
if [ "$target" = "$canonical" ]; then
    echo "Refusing to restore over the canonical database." >&2
    exit 2
fi
exists=$(compose exec -T postgres sh -lc \
    "psql --username=\"\$POSTGRES_USER\" --dbname=postgres --tuples-only --no-align --command=\"SELECT 1 FROM pg_database WHERE datname='$target'\"" \
    | tr -d '\r')
if [ "$exists" = "1" ]; then
    echo "Refusing to restore into existing database: $target" >&2
    exit 2
fi

compose exec -T postgres sh -lc \
    "createdb --username=\"\$POSTGRES_USER\" '$target'"
compose exec -T postgres sh -lc \
    "pg_restore --username=\"\$POSTGRES_USER\" --dbname='$target' --no-owner --no-acl" < "$dump"
compose exec -T postgres sh -lc \
    "psql --username=\"\$POSTGRES_USER\" --dbname='$target' --command='SELECT count(*) AS migration_count FROM django_migrations'"
echo "Restore completed into new database: $target"
