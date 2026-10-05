#!/bin/sh
set -e

echo "applying migrations..."
alembic upgrade head

if [ "$1" = "scheduler" ]; then
    exec python -m app.scheduler
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
