#!/bin/sh
set -e

# Run migrations then start gunicorn
python manage.py migrate --noinput || true
python manage.py collectstatic --noinput || true
exec "${@:-gunicorn weatherProject.wsgi:application --bind 0.0.0.0:8000" 
