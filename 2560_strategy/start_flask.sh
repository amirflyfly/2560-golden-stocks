#!/bin/bash
set -e

if [ "${APP_ENV:-development}" = "production" ] || [ "${APP_ENV:-development}" = "prod" ]; then
    echo "start_flask.sh is a legacy SQLite/dev entrypoint. Use docker compose for production."
    exit 1
fi

echo "🚀 Starting 2560 Strategy System..."

if [ ! -f "data/picks.db" ]; then
    echo "📦 Initializing database..."
    python scripts/maintenance/init_tracker_db.py
fi

echo "🌐 Starting Flask web server..."
exec python app.py
