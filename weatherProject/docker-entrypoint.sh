#!/bin/sh
set -e

# Run migrations and collectstatic, ignore errors to avoid startup failure
python manage.py migrate --noinput || true
python manage.py collectstatic --noinput || true

# Use PORT env var if provided (Vercel sets $PORT), otherwise default 8000
: ${PORT:=8000}
exec "${@:-gunicorn weatherProject.wsgi:application --bind 0.0.0.0:${PORT}}"
