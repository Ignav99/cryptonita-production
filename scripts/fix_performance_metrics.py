"""
FIX PERFORMANCE METRICS — One-time equity curve correction
============================================================
The May 5 backfill inserted inflated portfolio_value rows (~$12K instead of ~$9.9K).
This script recalculates portfolio_value by walking forward from initial_capital
using the daily_pnl accumulated, producing a clean equity curve.

Usage:
    cd cryptonita-production
    python scripts/fix_performance_metrics.py [--dry-run]

Options:
    --dry-run   Show what would be fixed without writing to DB
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from src.data.storage.db_manager import DatabaseManager
from loguru import logger


def fix_equity_curve(dry_run: bool = False):
    db = DatabaseManager(settings.get_database_url())

    logger.info("Fetching performance_metrics rows ordered by date...")
    rows_df = db.execute_query("""
        SELECT id, date, daily_pnl, portfolio_value
        FROM performance_metrics
        ORDER BY date ASC
    """)

    if rows_df.empty:
        logger.warning("No rows found in performance_metrics. Nothing to fix.")
        return

    CAPITAL_START = 10000.0
    running = CAPITAL_START
    fixes = []

    for _, row in rows_df.iterrows():
        daily_pnl = float(row["daily_pnl"]) if row["daily_pnl"] is not None else 0.0
        running += daily_pnl
        old_value = float(row["portfolio_value"]) if row["portfolio_value"] is not None else 0.0
        fixes.append({
            "id": int(row["id"]),
            "date": row["date"],
            "old_value": round(old_value, 2),
            "new_value": round(running, 2),
            "daily_pnl": round(daily_pnl, 2),
        })

    logger.info(f"Found {len(fixes)} rows to update.")
    logger.info(f"First date: {fixes[0]['date']} | Last date: {fixes[-1]['date']}")
    logger.info(f"Final portfolio value (corrected): ${fixes[-1]['new_value']:.2f}")

    # Show preview
    print("\n=== PREVIEW (first 10 rows) ===")
    for f in fixes[:10]:
        diff = f["new_value"] - f["old_value"]
        marker = " ← CHANGED" if abs(diff) > 0.01 else ""
        print(f"  {f['date']} | pnl={f['daily_pnl']:+.2f} | old={f['old_value']:.2f} → new={f['new_value']:.2f}{marker}")

    print(f"\n=== FINAL VALUE ===")
    print(f"  Old final: ${fixes[-1]['old_value']:.2f}")
    print(f"  New final: ${fixes[-1]['new_value']:.2f}")

    if dry_run:
        logger.info("DRY RUN mode — no changes written to database.")
        return

    confirm = input("\nProceed with update? [y/N] ").strip().lower()
    if confirm != "y":
        logger.info("Aborted.")
        return

    updated = 0
    for f in fixes:
        if abs(f["new_value"] - f["old_value"]) > 0.001:
            db.execute_command(
                "UPDATE performance_metrics SET portfolio_value = :val WHERE id = :id",
                {"val": f["new_value"], "id": f["id"]},
            )
            updated += 1

    logger.success(f"Updated {updated} rows. Equity curve corrected.")
    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix equity curve corruption in performance_metrics")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to DB")
    args = parser.parse_args()
    fix_equity_curve(dry_run=args.dry_run)
