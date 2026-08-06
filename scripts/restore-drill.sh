#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: restore-drill.sh FILE" >&2
    exit 2
fi
dump=$1
test -s "$dump" || { echo "Backup dump is missing or empty: $dump" >&2; exit 2; }

image='postgres:18.4-alpine@sha256:9a8afca54e7861fd90fab5fdf4c42477a6b1cb7d293595148e674e0a3181de15'
container="ftl-restore-drill-$$"
password="restore-drill-$$-temporary" # pragma: allowlist secret
cleanup() {
    docker stop --time 3 "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker run --detach --rm --name "$container" \
    --tmpfs /var/lib/postgresql \
    --env POSTGRES_DB=ftl_restore_drill \
    --env POSTGRES_USER=ftl_restore \
    --env POSTGRES_PASSWORD="$password" \
    "$image" >/dev/null

attempt=0
until docker exec "$container" pg_isready --username=ftl_restore --dbname=ftl_restore_drill >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "Restore-drill PostgreSQL did not become ready." >&2
        exit 1
    fi
    sleep 1
done

docker run --rm -i --entrypoint pg_restore "$image" --list < "$dump" > /dev/null
docker exec -i "$container" pg_restore \
    --username=ftl_restore \
    --dbname=ftl_restore_drill \
    --no-owner \
    --no-acl < "$dump"
migration_count=$(docker exec "$container" psql \
    --username=ftl_restore \
    --dbname=ftl_restore_drill \
    --tuples-only \
    --no-align \
    --command='SELECT count(*) FROM django_migrations' | tr -d '\r')
if [ "$migration_count" -lt 1 ]; then
    echo "Restore drill found no Django migration records." >&2
    exit 1
fi
echo "Restore drill passed with $migration_count applied migration records."
