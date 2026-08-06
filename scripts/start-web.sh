#!/bin/sh
set -eu

python manage.py validate_runtime
python manage.py migrations_applied_check

if [ "${APP_ENV:-development}" = "production" ]; then
    python manage.py check --deploy
else
    python manage.py check
fi

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout "${GUNICORN_TIMEOUT_SECONDS:-120}" \
    --access-logfile - \
    --error-logfile -
