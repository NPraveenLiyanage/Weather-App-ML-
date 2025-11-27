#!/bin/sh
set -e

# Collect static files at container start (safe); migrations should be run separately
python manage.py collectstatic --noinput || true

# Use PORT env var if provided (Vercel sets $PORT), otherwise default 8000
: "${PORT:=8000}"
if [ -z "$1" ]; then
exec gunicorn weatherProject.wsgi:application --bind 0.0.0.0:${PORT}
else
exec "$@"
fi