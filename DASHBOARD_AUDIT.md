# Dashboard Audit - PnL Fix & Complete Logic Reference

**Date:** 2026-05-07 (updated 2026-05-11)
**Status:** Fixed and deployed (two rounds of fixes)
**Bug severity:** Critical

---

## Bug #2 Found: Zombie Positions with Corrupted PnL (May 11, 2026)

### Root Cause

Two issues combined:

1. **`_execute_exit()` left zombie positions**: When dust/rounding made sell impossible, it set `remaining_quantity=0` but did NOT delete the row or clear `pnl`/`total_value`. Result: positions with qty=0 but PnL of -$17 million (e.g. FLOKIUSDT).

2. **Some full-exit callers forgot `db.delete_position()`**: The `exit_full` and `stop_loss` paths in `_monitor_positions` did `del self.positions[ticker]` (memory only) but never called `db.delete_position()`.

3. **Stats queries had no filter**: `get_dashboard_stats()` summed `pnl`, `total_value`, and counted positions from ALL rows in `positions` table — including zombies with millions in corrupted PnL.

### Data Found in Production

| Position | remaining_qty | PnL | total_value |
|----------|--------------|-----|-------------|
| FLOKIUSDT | 0 | -$17,457,293 | -$152,512,890 |
| MANTAUSDT | 0 | -$6,164 | -$114,512 |
| ALGOUSDT | 0 | -$5,564 | -$77,719 |
| IMXUSDT | 0 | -$2,802 | -$25,065 |
| APTUSDT | 0 | -$473 | -$5,932 |
| **5 dust total** | **0** | **-$17,472,298** | |
| **6 real positions** | **>0** | **-$13.54** | |

### Fix Applied

1. **`_execute_exit()`**: Dust/rounding paths now call `db.delete_position()` instead of `UPDATE remaining_quantity=0`
2. **Full exit paths**: Added `db.delete_position(ticker)` after `exit_full` and `stop_loss` in `_monitor_positions`
3. **Bot startup**: Dust cleanup now calls `db.delete_position()` instead of UPDATE
4. **`get_dashboard_stats()`**: All 3 positions queries now filter `WHERE remaining_quantity > 0.0001`
5. **`sync_portfolio_invested()`**: Also filters dust positions

### Files Modified

| File | Changes |
|------|---------|
| `src/data/storage/db_manager.py` | 4 queries: added `WHERE remaining_quantity > 0.0001` |
| `src/bot/trading_bot.py` | 5 fixes: delete_position instead of UPDATE qty=0, added missing delete calls |

---

## Bug #1 Found: Cross-Join PnL Calculation (May 7, 2026)

### Root Cause

ALL PnL queries used a self-join pattern that created a **cross product** of BUYs and SELLs per ticker:

```sql
-- BROKEN (was in 11 locations)
FROM trades b
INNER JOIN trades s ON b.ticker = s.ticker AND s.timestamp > b.timestamp
WHERE b.action = 'BUY' AND s.action = 'SELL'
```

This pairs **every BUY** with **every later SELL** for the same ticker. If a ticker has 3 BUYs and 3 SELLs, it produces 9 pairs instead of 3 correct FIFO pairs. With dozens of tickers and repeated trades, the error compounds exponentially.

### Fix Applied

Replaced with **FIFO matching via ROW_NUMBER()** — BUY #1 matches SELL #1, BUY #2 matches SELL #2, etc:

```sql
-- CORRECT (now in all 11 locations)
WITH numbered_buys AS (
    SELECT ticker, price, quantity,
           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp) as rn
    FROM trades WHERE action = 'BUY' AND status = 'executed'
),
numbered_sells AS (
    SELECT ticker, price, quantity,
           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp) as rn
    FROM trades WHERE action = 'SELL' AND status = 'executed'
)
SELECT COALESCE(SUM(
    (s.price - b.price) * LEAST(b.quantity, s.quantity)
), 0) as realized_pnl
FROM numbered_buys b
INNER JOIN numbered_sells s ON b.ticker = s.ticker AND b.rn = s.rn
```

### Files Modified (11 query instances)

| File | Function | Query Purpose |
|------|----------|---------------|
| `src/data/storage/db_manager.py` | `get_closed_positions()` | Matched BUY/SELL pairs display |
| `src/data/storage/db_manager.py` | `backfill_performance_metrics()` | Per-day closed PnL |
| `src/data/storage/db_manager.py` | `snapshot_daily_performance()` | Cumulative realized PnL |
| `src/data/storage/db_manager.py` | `snapshot_daily_performance()` | Win rate calculation |
| `src/data/storage/db_manager.py` | `get_dashboard_stats()` | Realized PnL for stats |
| `src/data/storage/db_manager.py` | `get_dashboard_stats()` | Win rate for stats |
| `src/data/storage/db_manager.py` | `get_dashboard_stats()` | Today's PnL |
| `src/api/routes/dashboard.py` | `recalibrate_portfolio()` | Portfolio recalibration PnL |
| `src/api/main.py` | startup `@app.on_event("startup")` | Boot-time portfolio recalibration |
| `src/api/main.py` | `_generate_review_report()` | Period PnL + win/loss counts |
| `src/api/main.py` | `_generate_review_report()` | Best/worst trades ranking |

---

## Complete Dashboard Data Flow

### API Endpoints

| Endpoint | Method | Polls (frontend) | Description |
|----------|--------|-------------------|-------------|
| `/api/dashboard/stats` | GET | 15s | Portfolio value, PnL, win rate, today PnL |
| `/api/dashboard/bot-status` | GET | 10s | Bot running status |
| `/api/dashboard/positions` | GET | 15s | Open positions with unrealized PnL |
| `/api/dashboard/closed-positions` | GET | 30s | Matched BUY/SELL pairs with realized PnL |
| `/api/dashboard/trades` | GET | 30s | Raw trade history |
| `/api/dashboard/performance` | GET | 60s | Daily performance for equity curve |
| `/api/dashboard/signals` | GET | 15s | Recent signals |
| `/api/dashboard/portfolio-value` | GET | on-demand | Portfolio breakdown |
| `/api/dashboard/portfolio/recalibrate` | POST | on-demand | Fix portfolio from actual trades |
| `/api/dashboard/backfill-performance` | POST | on-demand | Rebuild performance_metrics table |
| `wss://host/api/ws/dashboard` | WS | real-time | Push stats, bot_status, positions |

### PnL Calculation Chain

```
1. TRADE EXECUTION (trading_bot.py)
   - BUY: deduct_from_balance(amount) -> portfolio.available_balance -= amount, portfolio.total_invested += amount
   - SELL: add_to_balance(amount, pnl) -> portfolio.available_balance += amount, portfolio.total_invested -= cost_basis, portfolio.realized_pnl += pnl
   - PnL at sell time: sale_pnl = (executed_price - entry_price) * executed_qty  [CORRECT, per-trade]

2. DASHBOARD STATS (/api/dashboard/stats -> get_dashboard_stats())
   - realized_pnl: FIFO-matched BUY/SELL pairs from trades table
   - unrealized_pnl: SUM(pnl) from positions table (updated by bot monitor loop)
   - total_pnl: realized + unrealized
   - total_pnl_pct: total_pnl / initial_capital * 100
   - win_rate: count(pnl > 0) / count(*) from FIFO pairs * 100
   - today_pnl: FIFO pairs where SELL timestamp >= today 00:00 UTC
   - portfolio_value: OVERRIDDEN with portfolio.available_balance + portfolio.total_invested

3. PORTFOLIO TABLE (single row, id=1)
   - initial_capital: 10000.0 (fixed)
   - available_balance: USDT ready to trade
   - total_invested: cost basis of open positions
   - realized_pnl: cumulative closed PnL (incremental via add_to_balance)
   - total_value: available_balance + total_invested

4. RECALIBRATION (startup + /portfolio/recalibrate)
   - real_invested = SUM(remaining_quantity * avg_buy_price) from positions
   - realized_pnl = FIFO-matched sum from trades
   - available_balance = 10000.0 + realized_pnl - real_invested
   - Updates portfolio table to match reality

5. EQUITY CURVE (/api/dashboard/performance)
   - Reads from performance_metrics table (snapshotted daily by bot)
   - Each row: date, portfolio_value, total_pnl (cumulative), win_rate
   - Backfill rebuilds from trade history
```

### Frontend Display

```
Overview.jsx
  - StatCard "Portfolio": stats.portfolio_value (from portfolio table total_value)
  - StatCard "Total PnL": stats.total_pnl (realized + unrealized, FIFO-matched)
  - StatCard "Win Rate": stats.win_rate
  - StatCard "Open Positions": stats.active_positions

Positions.jsx
  - Open positions: from /positions, PnL per position from positions.pnl
  - Closed positions: from /closed-positions, FIFO-matched pairs

EquityCurve.jsx
  - Chart: performance_metrics.portfolio_value over time
  - Source: /performance?days=30
```

### Critical Patterns

1. **Raw dicts for API responses**: PostgreSQL NUMERIC -> Decimal breaks Pydantic v2. Solution: bypass Pydantic, return raw dicts with manual float/isoformat/str conversion. Used in `/trades`, `/performance`, `/closed-positions`.

2. **Portfolio values override DB stats**: In `/stats` endpoint, `portfolio_value`, `usdt_balance`, and `positions_value` come from portfolio table (cost basis), NOT from live market prices.

3. **positions.pnl is updated in bot loop**: `_monitor_positions()` updates each position's PnL using current prices. This is the only source of unrealized PnL.

---

## Verification Checklist

After deploying this fix:

- [ ] `/api/dashboard/stats` returns reasonable PnL (should be small +/- around $0-500 range for ~120 trades)
- [ ] `/api/dashboard/closed-positions` shows 1:1 matched pairs (no duplicates per ticker cycle)
- [ ] Win rate is between 0-100% (not inflated by phantom pairs)
- [ ] Portfolio recalibrate endpoint returns sane available_balance (positive, < initial_capital + realized_pnl)
- [ ] Equity curve shows gradual changes, not wild swings
- [ ] Today PnL only reflects sells from today

## Post-Deploy Actions Required

1. **Recalibrate portfolio**: Call `POST /api/dashboard/portfolio/recalibrate` to fix the portfolio table with correct FIFO PnL
2. **Re-backfill performance**: Call `POST /api/dashboard/backfill-performance` to rebuild equity curve with correct data
3. Both actions happen automatically on next deploy/restart (startup recalibrate + backfill if empty)
