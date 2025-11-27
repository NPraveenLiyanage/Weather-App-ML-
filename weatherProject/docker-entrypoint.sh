#!/bin/sh
set -e

APP_ROOT="/app"
PROJECT_ROOT="$APP_ROOT/weatherProject"

# Ensure Django project is importable regardless of working dir
export PYTHONPATH="$APP_ROOT:$PROJECT_ROOT:${PYTHONPATH:-}"

# Collect static files at container start (safe); migrations should be run separately
python "$PROJECT_ROOT/manage.py" collectstatic --noinput || true

# Ensure we always bind to the port Render provides (default 8000 when unset)
PORT="${PORT:-8000}"

if [ "$1" = "gunicorn" ]; then
	shift
	exec gunicorn "$@" --bind "0.0.0.0:${PORT}"
fi

exec "$@"