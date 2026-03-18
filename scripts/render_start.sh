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
python scripts/migrate_model_artifacts.py || echo "⚠️ Model artifacts migration already applied"

# Clean positions table (remove positions not opened by bot)
echo "🧹 Cleaning positions table..."
python scripts/clean_positions.py || echo "⚠️ Position cleaning skipped"

# Seed model to DB if needed (for V4 model persistence across Render restarts)
echo "🤖 Checking model artifacts in DB..."
python -c "
import sys
sys.path.insert(0, '.')
from config import settings
if getattr(settings, 'USE_V4_MODEL', False):
    from src.models.model_store import ModelStore
    from pathlib import Path
    store = ModelStore()
    if not store.has_active_model():
        model_dir = getattr(settings, 'V4_MODEL_DIR', 'PRODUCTION_SYSTEM/models/v4')
        if Path(model_dir).exists() and (Path(model_dir) / 'ensemble_metadata.json').exists():
            print('Seeding V4 model from filesystem to DB...')
            version = store.get_latest_version() + 1
            store.save_ensemble(version, model_dir)
            store.promote_version(version)
            print(f'Seeded model v{version} to DB')
        else:
            print('No filesystem model found — bot will auto-train on first cycle')
    else:
        print(f'Active model found in DB (v{store.get_latest_version()})')
else:
    print('V4 model disabled, skipping model seeding')
" || echo "⚠️ Model seeding skipped"

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