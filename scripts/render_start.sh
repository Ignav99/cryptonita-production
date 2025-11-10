#!/bin/bash
# Render Start Script
set -e

echo "🚀 Starting Cryptonita Production System..."

# Parse DATABASE_URL if it exists and create individual env vars
if [ -n "$DATABASE_URL" ]; then
    echo "📊 Configuring database connection..."
    # Parse PostgreSQL URL: postgresql://user:password@host:port/database
    export DB_USER=$(echo $DATABASE_URL | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
    export DB_PASSWORD=$(echo $DATABASE_URL | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p')
    export DB_HOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\):.*/\1/p')
    export DB_PORT=$(echo $DATABASE_URL | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
    export DB_NAME=$(echo $DATABASE_URL | sed -n 's/.*\/\(.*\)/\1/p')
fi

# Run database setup/migrations
echo "📊 Setting up database..."
python scripts/setup_database.py || echo "⚠️ Database already exists or migration skipped"
python scripts/migrate_positions_table.py || echo "⚠️ Migration already applied or skipped"

# Start the API server (which will serve the frontend too)
echo "🌐 Starting API server..."
echo "📍 API will be available at: https://cryptonita-bot.onrender.com"
echo "🤖 Bot can be controlled via the dashboard"

# Use gunicorn for production with uvicorn workers
gunicorn src.api.main:app \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${API_PORT:-8000} \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
