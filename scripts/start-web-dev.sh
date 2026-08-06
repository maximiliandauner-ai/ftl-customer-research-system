#!/bin/sh
set -eu

python manage.py validate_runtime
python manage.py migrations_applied_check
python manage.py check

exec python manage.py runserver 0.0.0.0:8000
