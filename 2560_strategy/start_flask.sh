#!/bin/bash
set -e

echo "🚀 Starting 2560 Strategy System..."

if [ ! -f "data/picks.db" ]; then
    echo "📦 Initializing database..."
    python init_tracker_db.py
fi

echo "🌐 Starting Flask web server..."
exec python app.py
