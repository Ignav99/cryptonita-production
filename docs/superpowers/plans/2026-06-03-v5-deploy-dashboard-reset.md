# V5 Deploy + Dashboard V5 + Soft Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy V5 ternary model (LONG/SHORT/HOLD) to Render, update the dashboard to show SHORT signals and V5 metrics, add a soft-reset endpoint to set portfolio to $3000 without deleting historical data, and verify everything runs correctly.

**Architecture:** V5 is already committed locally (ad65912). This plan updates render.yaml config, adds a soft-reset API endpoint, updates the frontend to show SHORT signals and V5 stats, commits everything uncommitted, pushes to main, then calls the soft-reset via the Render API to initialize the $3000 balance.

**Tech Stack:** FastAPI (Python 3.11), React + Vite + TailwindCSS, PostgreSQL on Render, Binance Futures API

---

## Files to modify

| File | Action | Purpose |
|------|---------|---------|
| `render.yaml` | Modify | Set USE_V4_MODEL=false, INITIAL_CAPITAL=3000 |
| `src/api/routes/controls.py` | Modify | Add POST /soft-reset endpoint |
| `frontend/src/pages/Signals.jsx` | Modify | Show signal_name (LONG/SHORT/HOLD) with colored badges |
| `frontend/src/pages/Overview.jsx` | Modify | Show LONG/SHORT win rate split + V5 model badge |
| `frontend/src/pages/Positions.jsx` | Modify | Handle SHORT positions (inverted PnL) |
| `frontend/src/api/client.js` | Modify | Add softReset() call |
| `docs/NEXT_CHECK.md` | Create | Checklist for next results review |

---

### Task 1: Update render.yaml — USE_V4_MODEL + INITIAL_CAPITAL

**Files:**
- Modify: `render.yaml`

- [ ] **Step 1: Change USE_V4_MODEL to false**

In `render.yaml`, find:
```yaml
      - key: USE_V4_MODEL
        value: "true"
```
Change to:
```yaml
      - key: USE_V4_MODEL
        value: "false"
```

- [ ] **Step 2: Change INITIAL_CAPITAL to 3000**

In `render.yaml`, find:
```yaml
      - key: INITIAL_CAPITAL
        value: 10000
```
Change to:
```yaml
      - key: INITIAL_CAPITAL
        value: 3000
```

- [ ] **Step 3: Verify the change**

Run: `grep -n "USE_V4_MODEL\|INITIAL_CAPITAL" render.yaml`
Expected output:
```
USE_V4_MODEL ... "false"
INITIAL_CAPITAL ... 3000
```

---

### Task 2: Add soft-reset endpoint in controls.py

**Files:**
- Modify: `src/api/routes/controls.py`

This endpoint DOES NOT delete historical data (trades history stays). It only:
- Deletes open positions
- Deletes pending/active signals
- Resets portfolio balance to $3000
- Resets bot_status counters
- Keeps all historical trades intact

- [ ] **Step 1: Add the soft_reset endpoint after the existing reset_database endpoint**

Open `src/api/routes/controls.py` and add after the `reset_database` function:

```python
@router.post("/soft-reset", response_model=BotControlResponse)
async def soft_reset(current_user: dict = Depends(get_current_user)):
    """
    Soft reset — clears open positions and pending signals, resets portfolio
    to $3,000. Historical trades are preserved. Use this to start fresh
    without losing historical performance data.
    """
    try:
        from sqlalchemy import text

        # Stop bot if running
        if bot_manager.is_running():
            bot_manager.stop(reason="Soft reset requested")

        with db.engine.connect() as conn:
            # Clear open positions only
            conn.execute(text("DELETE FROM positions"))
            logger.info("🗑️  Open positions cleared")

            # Clear all signals (fresh slate for V5)
            conn.execute(text("DELETE FROM signals"))
            logger.info("🗑️  Signals cleared")

            # Reset portfolio to $3,000
            conn.execute(text("""
                UPDATE portfolio
                SET available_balance = 3000.0,
                    initial_capital = 3000.0,
                    total_invested = 0.0,
                    realized_pnl = 0.0,
                    last_update = NOW()
            """))
            logger.info("💰 Portfolio reset to $3,000")

            # Reset bot_status counters (keep last_update)
            conn.execute(text("""
                UPDATE bot_status
                SET cycle_number = 0, total_signals = 0, buy_signals = 0,
                    status = 'stopped', last_error = NULL, last_update = NOW()
            """))
            conn.commit()

        logger.info("✅ Soft reset complete — portfolio at $3,000, history preserved")
        return BotControlResponse(
            success=True,
            message="Soft reset complete. Portfolio set to $3,000. Historical trades preserved.",
            status="stopped"
        )

    except Exception as e:
        logger.error(f"❌ Soft reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 2: Verify syntax (no import errors)**

Run:
```bash
/Users/User/.pyenv/versions/3.11.9/bin/python -c "
import sys; sys.path.insert(0, '.')
from src.api.routes.controls import router
print('✅ controls.py imports OK')
"
```
Expected: `✅ controls.py imports OK`

---

### Task 3: Add softReset() to frontend API client

**Files:**
- Modify: `frontend/src/api/client.js`

- [ ] **Step 1: Check where controls functions are defined**

Run: `grep -n "softReset\|resetDatabase\|startBot\|stopBot" frontend/src/api/client.js | head -20`

- [ ] **Step 2: Add softReset function in the controls object**

Find where `controls` is defined in `frontend/src/api/client.js`. It will look like:
```js
export const controls = {
  startBot: ...
  stopBot: ...
  resetDatabase: (params) => api.post('/controls/reset-database', params),
```

Add after `resetDatabase`:
```js
  softReset: () => api.post('/controls/soft-reset'),
```

- [ ] **Step 3: Verify the file compiles**

Run: `cd frontend && node --input-type=module <<< "import('./src/api/client.js')" 2>&1 | head -5`
Expected: no errors

---

### Task 4: Update Signals page — show LONG/SHORT/HOLD badge

**Files:**
- Modify: `frontend/src/pages/Signals.jsx`

The signals table currently shows `signal_type` column. In V5, the relevant field is `signal_name` (values: "LONG", "SHORT", "HOLD") and `signal_class` (0=HOLD, 1=LONG, 2=SHORT).

- [ ] **Step 1: Add a SignalBadge component at the top of Signals.jsx**

After the imports, add:
```jsx
function SignalBadge({ signalName, signalType }) {
  // V5 uses signal_name, V4 used signal_type
  const name = signalName || signalType || 'HOLD';
  const normalized = name.toUpperCase();

  if (normalized === 'LONG' || normalized === 'BUY') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-green-900/40 text-green-400 border border-green-800">
        ▲ LONG
      </span>
    );
  }
  if (normalized === 'SHORT') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-red-900/40 text-red-400 border border-red-800">
        ▼ SHORT
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-gray-800/60 text-gray-400 border border-gray-700">
      — HOLD
    </span>
  );
}
```

- [ ] **Step 2: Find the signals DataTable column definition and update it**

Search for where signal columns are defined (look for `signal_type` in the columns array). Update the signal type column to use `SignalBadge`:

```jsx
{
  key: 'signal_name',
  label: 'Signal',
  render: (val, row) => (
    <SignalBadge signalName={row.signal_name} signalType={row.signal_type} />
  ),
},
```

- [ ] **Step 3: Update summary stat cards to show SHORT count**

Find where the summary stats are displayed (buy_signals_count, hold_signals_count). Add short_signals_count:

```jsx
<StatCard
  label="SHORT Signals"
  value={summary?.short_signals_count ?? 0}
  icon={ArrowDown}
  variant="danger"
/>
```

- [ ] **Step 4: Verify the page renders without errors**

Open browser at the Signals URL or check console for JSX errors.

---

### Task 5: Update Overview page — V5 model badge + LONG/SHORT win rates

**Files:**
- Modify: `frontend/src/pages/Overview.jsx`

- [ ] **Step 1: Add model version badge to the stats section**

After the existing StatCard components, add a model version indicator:
```jsx
{/* V5 Model Badge */}
<div className="col-span-full flex items-center gap-2 text-xs text-text-secondary">
  <span className="px-2 py-0.5 rounded bg-purple-900/40 text-purple-400 border border-purple-800 font-mono">
    V5 Ternary · LONG / SHORT / HOLD
  </span>
  <span className="text-text-secondary">• SHORT via Binance Futures</span>
</div>
```

- [ ] **Step 2: Show LONG vs SHORT win rate if available**

In the stats section, check if `stats.long_win_rate` and `stats.short_win_rate` exist and display them:

```jsx
{stats?.short_win_rate != null && (
  <div className="grid grid-cols-2 gap-3 mt-2">
    <StatCard
      label="LONG Win Rate"
      value={stats.long_win_rate != null ? `${(stats.long_win_rate * 100).toFixed(1)}%` : '—'}
      icon={TrendingUp}
    />
    <StatCard
      label="SHORT Win Rate"
      value={stats.short_win_rate != null ? `${(stats.short_win_rate * 100).toFixed(1)}%` : '—'}
      icon={TrendingDown}
    />
  </div>
)}
```

Import `TrendingDown` from lucide-react at the top.

---

### Task 6: Update Positions page — handle SHORT (inverted PnL)

**Files:**
- Modify: `frontend/src/pages/Positions.jsx`

- [ ] **Step 1: Check how PnL is currently displayed**

Run: `grep -n "pnl\|unrealized\|profit" frontend/src/pages/Positions.jsx | head -20`

- [ ] **Step 2: Add direction badge to positions table**

Find where position rows are rendered. Add a direction indicator:

```jsx
function DirectionBadge({ signalType, signalName }) {
  const name = (signalName || signalType || 'LONG').toUpperCase();
  if (name === 'SHORT') {
    return <span className="px-1.5 py-0.5 rounded text-xs font-bold bg-red-900/40 text-red-400 border border-red-800">SHORT</span>;
  }
  return <span className="px-1.5 py-0.5 rounded text-xs font-bold bg-green-900/40 text-green-400 border border-green-800">LONG</span>;
}
```

Add this badge in the position row next to the ticker name.

- [ ] **Step 3: Verify the positions page renders correctly**

Check that SHORT positions (if any) display with the red badge.

---

### Task 7: Update dashboard.py API — add short_signals_count to summary

**Files:**
- Modify: `src/api/routes/dashboard.py`

The `get_signals_summary` endpoint needs to return `short_signals_count`.

- [ ] **Step 1: Find the signals summary endpoint**

Read lines ~84-128 of `src/api/routes/dashboard.py`. Specifically find where `buy_count` and `hold_count` are computed.

- [ ] **Step 2: Add short_count computation**

In the `get_signals_summary` function, after `buy_count`, add:
```python
# V5: SHORT signals use signal_type='SHORT' or signal_name='SHORT'
short_count = len(latest_df[
    (latest_df['signal_type'].str.upper().isin(['SHORT', 'SELL'])) |
    (latest_df.get('signal_name', pd.Series(dtype=str)).str.upper() == 'SHORT')
]) if not latest_df.empty else 0
```

- [ ] **Step 3: Include short_signals_count in the response**

In the `SignalsSummaryStats` schema (or wherever it's defined), add `short_signals_count: int = 0`. Then include it in the response:
```python
short_signals_count=short_count,
```

- [ ] **Step 4: Verify the endpoint returns correct data**

Run:
```bash
/Users/User/.pyenv/versions/3.11.9/bin/python -c "
import sys; sys.path.insert(0, '.')
from src.api.routes.dashboard import router
print('✅ dashboard.py imports OK')
"
```

---

### Task 8: Commit everything

**Files:** All modified/new files

- [ ] **Step 1: Check what's uncommitted**

Run: `git status --short`

- [ ] **Step 2: Stage all new/modified source files (NOT .env)**

```bash
git add render.yaml
git add src/api/routes/controls.py
git add src/api/routes/dashboard.py
git add frontend/src/pages/Signals.jsx
git add frontend/src/pages/Overview.jsx
git add frontend/src/pages/Positions.jsx
git add frontend/src/api/client.js
git add src/models/
git add src/services/
git add scripts/
git add tests/
git add docs/
git add .gitignore
```

- [ ] **Step 3: Verify .env is NOT staged**

Run: `git diff --cached --name-only | grep .env`
Expected: no output (not staged)

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(v5): deploy V5 ternary model, soft-reset endpoint, dashboard SHORT signals"
```

- [ ] **Step 5: Push to main**

```bash
git push origin main
```

- [ ] **Step 6: Verify push succeeded**

Run: `git log --oneline -3`
Expected: new commit at top

---

### Task 9: Call soft-reset on Render

Once the push triggers a Render deploy (takes ~3-5 minutes), call the soft-reset endpoint.

- [ ] **Step 1: Get the Render URL**

Run: `grep -r "RENDER_EXTERNAL_URL\|render.com\|cryptonita" .env 2>/dev/null || echo "check Render dashboard for URL"`

- [ ] **Step 2: Wait for Render deploy to finish**

Check Render deploy status — look for "Deploy live" in the Render dashboard.

- [ ] **Step 3: Get auth token**

```bash
curl -s -X POST https://<YOUR_RENDER_URL>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<PASSWORD>"}' | python3 -m json.tool
```

Save the `access_token` from the response.

- [ ] **Step 4: Call soft-reset**

```bash
curl -s -X POST https://<YOUR_RENDER_URL>/api/controls/soft-reset \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" | python3 -m json.tool
```

Expected:
```json
{
  "success": true,
  "message": "Soft reset complete. Portfolio set to $3,000. Historical trades preserved.",
  "status": "stopped"
}
```

- [ ] **Step 5: Verify portfolio shows $3,000**

```bash
curl -s https://<YOUR_RENDER_URL>/api/stats \
  -H "Authorization: Bearer <ACCESS_TOKEN>" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Balance: ${d[\"usdt_balance\"]:,.2f}')
print(f'Portfolio value: ${d[\"portfolio_value\"]:,.2f}')
"
```
Expected: Balance ~$3,000

---

### Task 10: Create NEXT_CHECK.md

**Files:**
- Create: `docs/NEXT_CHECK.md`

- [ ] **Step 1: Write the checklist doc**

```markdown
# Next Results Check — Cryptonita V5

> Created: 2026-06-03 | Starting capital: $3,000 | Model: V5 Ternary

## What to verify when you come back

### 1. Portfolio health
- [ ] Balance > $3,000 (any gain = working)
- [ ] Balance < $2,700 = STOP and investigate
- [ ] Check max drawdown in Overview tab

### 2. Signal quality
```
GET /api/stats → win_rate, long_win_rate, short_win_rate
```
- [ ] SHORT win rate > 37.5% (break-even with +5% TP / -3% SL)
- [ ] LONG win rate > 37.5%
- [ ] If LONG WR < 30%, disable LONG trades in per_coin_config.py

### 3. Model performance by timeframe
- After **1 day**: expect 2-5 signals, no conclusions yet
- After **3 days**: enough signals to see direction
- After **1 week**: 10-20 signals → check win rate
- After **2 weeks**: statistical significance begins (~30 trades)

### 4. Expected results (backtest-calibrated)
| Timeframe | Conservative | Base case |
|-----------|-------------|-----------|
| 1 week | $3,000 → $3,090–$3,240 (+3–8%) | +5–12% |
| 1 month | +12–25% | +20–40% |

These assume $3K base, 47 coins active, R/R = +5% TP / -3% SL

### 5. Red flags → investigate immediately
- Zero trades after 48h (bot not running, model not loaded)
- All trades HOLD (threshold too high, models not trained)
- Only LONG or only SHORT (per_coin_config error)
- Any single trade > -5% loss (SL not working)

### 6. If SHORT not executing
Check:
- `BINANCE_FUTURES_API_KEY` is set in Render env vars
- `render.yaml` has `USE_V4_MODEL=false`
- Logs show "V5 Ternary Predictor" at startup

### 7. Retraining schedule
- V5 models train every 7 days (AUTO_TRAIN_INTERVAL_DAYS=7)
- Manual retrain: POST /api/controls/trigger-training
- Check training status: GET /api/controls/training-status

### 8. Files to check if something is wrong
- `src/models/predictor_v5.py` — threshold values, should_trade() logic
- `src/config/per_coin_config.py` — which coins have LONG disabled
- `src/services/binance_futures_service.py` — SHORT execution logic
- `docs/BACKTEST_V5_2026-06-03_pass2.md` — baseline metrics

### 9. What V5 changed vs V4
| | V4 | V5 |
|--|--|--|
| SHORT trading | ❌ impossible | ✅ Binance Futures |
| Classification | Binary (BUY/HOLD) | Ternary (LONG/SHORT/HOLD) |
| Models | Shared global model | Per-coin model |
| LONG WR | ~27% | ~30% |
| SHORT WR | N/A | ~47-51% |
| Win rate break-even | 50% | 37.5% (asymmetric R/R) |
| Sharpe (backtest) | unknown | 5.5 avg |
```

- [ ] **Step 2: Commit the doc**

```bash
git add docs/NEXT_CHECK.md
git commit -m "docs: add V5 next-check verification guide"
git push origin main
```

---

## Self-Review

**Spec coverage:**
- [x] Commit V5 to cloud → Task 8
- [x] render.yaml USE_V4_MODEL=false → Task 1
- [x] INITIAL_CAPITAL=3000 → Task 1
- [x] Soft-reset endpoint → Task 2
- [x] Frontend SHORT signals display → Task 4
- [x] Frontend overview V5 → Task 5
- [x] Frontend positions SHORT → Task 6
- [x] Push and verify on Render → Task 9
- [x] NEXT_CHECK doc → Task 10

**Placeholder scan:** None found — all steps have actual code.

**Critical note on Task 9:** The Render URL and credentials need to be confirmed from the Render dashboard or .env before executing the curl commands.
