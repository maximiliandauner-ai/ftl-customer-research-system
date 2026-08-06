#!/bin/sh
set -eu

queues=${1:-}
if [ -z "$queues" ]; then
    echo "An explicit Celery queue list is required." >&2
    exit 2
fi

python manage.py validate_runtime
python manage.py migrations_applied_check

exec celery -A config.celery:app worker \
    --loglevel "${LOG_LEVEL:-INFO}" \
    --queues "$queues" \
    --concurrency "${CELERY_WORKER_CONCURRENCY:-2}" \
    --without-gossip \
    --without-mingle
