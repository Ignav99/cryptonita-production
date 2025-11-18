#!/bin/bash
# Render Start Script
set -e

echo "🚀 Starting Cryptonita Production System..."

# Only parse DATABASE_URL if DB variables are not already set
if [ -z "$DB_PORT" ] && [ -n "$DATABASE_URL" ]; then
    echo "📊 Parsing DATABASE_URL..."
    # Parse PostgreSQL URL: postgresql://user:password@host:port/database
    export DB_USER=$(echo $DATABASE_URL | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
    export DB_PASSWORD=$(echo $DATABASE_URL | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p')
    export DB_HOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:/]*\).*/\1/p')
    export DB_PORT=$(echo $DATABASE_URL | sed -n 's/.*:\([0-9]\+\)\/.*/\1/p')
    # If port is empty, default to 5432
    if [ -z "$DB_PORT" ]; then
        export DB_PORT=5432
    fi
    export DB_NAME=$(echo $DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')

    echo "✅ Parsed DATABASE_URL - DB_PORT: ${DB_PORT}"
else
    echo "✅ Using DB variables from environment - DB_PORT: ${DB_PORT}"
fi

# Run database setup/migrations
echo "📊 Setting up database..."
python scripts/setup_database.py || echo "⚠️ Database already exists or migration skipped"
python scripts/migrate_positions_table.py || echo "⚠️ Migration already applied or skipped"
python scripts/migrate_add_probability_to_trades.py || echo "⚠️ Migration already applied or skipped"

# Clean positions table (remove positions not opened by bot)
echo "🧹 Cleaning positions table..."
python scripts/clean_positions.py || echo "⚠️ Position cleaning skipped"

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
