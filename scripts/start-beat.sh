#!/bin/sh
set -eu

python manage.py validate_runtime
python manage.py migrations_applied_check

exec celery -A config.celery:app beat \
    --loglevel "${LOG_LEVEL:-INFO}" \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler \
    --pidfile /tmp/ftl/celerybeat.pid \
    --schedule /tmp/ftl/celerybeat-schedule
