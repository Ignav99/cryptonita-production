#!/usr/bin/env python3
"""
Parse DATABASE_URL and set environment variables
"""
import os
import sys
from urllib.parse import urlparse

database_url = os.environ.get('DATABASE_URL', '')

if not database_url:
    print("ERROR: DATABASE_URL not set", file=sys.stderr)
    sys.exit(1)

try:
    url = urlparse(database_url)

    print(f"export DB_USER='{url.username or ''}'")
    print(f"export DB_PASSWORD='{url.password or ''}'")
    print(f"export DB_HOST='{url.hostname or ''}'")
    print(f"export DB_PORT='{url.port or 5432}'")
    print(f"export DB_NAME='{url.path.lstrip('/') or ''}'")

except Exception as e:
    print(f"ERROR parsing DATABASE_URL: {e}", file=sys.stderr)
    sys.exit(1)
