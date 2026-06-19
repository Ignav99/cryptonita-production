# V5 Backend + Frontend Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 0 LONG / 0 SHORT / 47 HOLD bug by correcting model save paths in training, and redesign the frontend to display V5 ternary signals correctly.

**Architecture:** Two parallel tracks — Backend fixes the model path mismatch (training saves to hardcoded path, predictor reads from V5_MODEL_DIR=/var/data/models/v5). Frontend fixes V5 display (BUY/SELL → LONG/SHORT, colors, stat cards).

**Tech Stack:** Python/FastAPI backend, React/Vite frontend, Render (Frankfurt), persistent disk at /var/data/

---

## ROOT CAUSE (confirmed via Render logs)

```
[V5] No global model found — predictions will return HOLD until training completes
```

At init time, `_load_global_model()` checks `settings.V5_MODEL_DIR / "global" / "v5_ensemble_metadata.json"`.
- `V5_MODEL_DIR=/var/data/models/v5` on Render
- Training likely saves to hardcoded `PRODUCTION_SYSTEM/models/v5/global/` which is ephemeral
- No model file exists at `/var/data/models/v5/global/` → all 47 coins → HOLD

---

## TRACK A: Backend Fix

**Files:**
- Read+Modify: `src/bot/trading_bot.py` (find training save path)
- Read+Modify: `src/models/ensemble_v5.py` (confirm save() method path)
- Read+Modify: `src/api/routes/controls.py` (add training trigger endpoint if missing)

### Task A1: Read and fix training save path

- [ ] Read `src/bot/trading_bot.py` — search for `v5/global`, `PRODUCTION_SYSTEM`, `save(`, `model_dir`
- [ ] Identify the exact path used when saving the trained global model
- [ ] If hardcoded: change to `str(Path(settings.V5_MODEL_DIR) / "global")`
- [ ] Add explicit log at save: `logger.success(f"[V5] Global model saved to {save_path}")`
- [ ] Verify `Path(settings.V5_MODEL_DIR).mkdir(parents=True, exist_ok=True)` is called before saving
- [ ] Commit: `fix(training): save global model to V5_MODEL_DIR persistent disk`

### Task A2: Add training trigger endpoint (if not exists)

- [ ] Check `src/api/routes/controls.py` for existing `/training/start` or `/retrain` endpoint
- [ ] If missing, add:
```python
@router.post("/training/start-v5")
async def start_v5_training(background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """Trigger V5 training cycle in background"""
    from src.bot.trading_bot import bot
    background_tasks.add_task(bot.run_training_cycle)
    return {"status": "training_started", "model_dir": str(settings.V5_MODEL_DIR)}
```
- [ ] Commit: `feat(api): add V5 training trigger endpoint`

### Task A3: Add debug logging to _load_global_model

- [ ] Edit `src/models/predictor_v5.py` `_load_global_model()`:
```python
def _load_global_model(self):
    global_dir = self.model_base_dir / "global"
    metadata_path = global_dir / "v5_ensemble_metadata.json"
    logger.info(f"[V5] Looking for global model at: {metadata_path} (exists={metadata_path.exists()})")
    if metadata_path.exists():
        ...
```
- [ ] Push all commits to trigger Render deploy
- [ ] Commit: `fix(predictor): add path debug logging to _load_global_model`

---

## TRACK B: Frontend Fix

**Files:**
- Modify: `frontend/src/components/charts/SignalDistribution.jsx`
- Modify: `frontend/src/pages/Signals.jsx`
- Modify: `src/api/routes/dashboard.py` (add signal_name to CoinSummary)
- Maybe: `frontend/src/api/client.js`

### Task B1: Fix SignalDistribution chart

**Problem:** COLORS only has BUY/SELL/HOLD. The chart counter uses `signal_type` not `signal_name`, so V5 signals (LONG/SHORT) don't get colored.

- [ ] Edit `frontend/src/components/charts/SignalDistribution.jsx`:
```javascript
const COLORS = {
  // V5 ternary
  LONG: '#3fb950',
  SHORT: '#f85149',
  HOLD: '#8b949e',
  // V4 legacy
  BUY: '#3fb950',
  SELL: '#f85149',
};

// In the counts reducer, prefer signal_name:
const counts = data.reduce((acc, s) => {
  const raw = (s.latest_signal_name || s.signal_name || s.latest_signal_type || s.signal_type || s.action || 'HOLD').toUpperCase();
  // Normalize V4 → V5
  const key = raw === 'BUY' ? 'LONG' : raw === 'SELL' ? 'SHORT' : raw;
  acc[key] = (acc[key] || 0) + 1;
  return acc;
}, {});
```
- [ ] Commit: `fix(frontend): update SignalDistribution for V5 LONG/SHORT/HOLD`

### Task B2: Fix Signals.jsx — All Signals tab filter labels

**Problem:** Filter buttons say `['ALL', 'BUY', 'SELL', 'HOLD']` instead of `['ALL', 'LONG', 'SHORT', 'HOLD']`

- [ ] Edit `frontend/src/pages/Signals.jsx` line ~389:
```javascript
// Change from:
{['ALL', 'BUY', 'SELL', 'HOLD'].map((f) => (
// To:
{['ALL', 'LONG', 'SHORT', 'HOLD'].map((f) => (
```
- [ ] Also fix the thresholds tab "Near Threshold" table column (line ~464):
```javascript
// Change from:
render: (v) => (
  <Badge variant={v === 'BUY' ? 'success' : v === 'SELL' ? 'danger' : 'neutral'}>{v}</Badge>
),
// To:
render: (v, row) => {
  const name = (row.signal_name || v || 'HOLD').toUpperCase();
  const variant = name === 'LONG' || name === 'BUY' ? 'success' : name === 'SHORT' || name === 'SELL' ? 'danger' : 'neutral';
  return <Badge variant={variant}>{name === 'BUY' ? 'LONG' : name === 'SELL' ? 'SHORT' : name}</Badge>;
},
```
- [ ] Commit: `fix(frontend): update signal filter labels to V5 LONG/SHORT`

### Task B3: Fix Stat Card — "Avg Probability" → useful V5 metric

**Problem:** "Avg Probability" is meaningless in V5 (probability of what — LONG? SHORT? HOLD?). Replace with HOLD% rate.

- [ ] Edit `frontend/src/pages/Signals.jsx` stat cards (line ~285):
```javascript
// Change the 4th stat card from:
<StatCard
  label="Avg Probability"
  value={summary?.avg_probability != null ? `${(summary.avg_probability * 100).toFixed(1)}%` : '—'}
  icon={Target}
/>
// To:
<StatCard
  label="HOLD Rate"
  value={summary != null && summary.total_coins_scanned > 0
    ? `${((summary.hold_signals_count / summary.total_coins_scanned) * 100).toFixed(0)}%`
    : '—'}
  icon={Target}
  subtitle={summary?.total_coins_scanned ? `${summary.total_coins_scanned} coins scanned` : undefined}
/>
```
- [ ] Commit: `fix(frontend): replace avg probability with HOLD rate stat card`

### Task B4: Fix dashboard.py /signals/coins — add signal_name to response

**Problem:** `CoinSummary` schema doesn't include `latest_signal_name` (the V5 ternary name). The frontend falls back to `latest_signal_type` which still contains old V4 values in some DB rows.

- [ ] Check `src/api/schemas/dashboard.py` for `CoinSummary` schema — add `latest_signal_name: Optional[str] = None`
- [ ] In `dashboard.py` `/signals/coins`, add `latest_signal_name=row.get('signal_name')` to `CoinSummary()` constructor
- [ ] Commit: `fix(api): add signal_name to CoinSummary response for V5 ternary`

---

## TRACK C: Post-Deploy Verification (runs after A+B deployed)

### Task C1: Verify deploy and trigger training

- [ ] Wait for Render deploy to complete (check via MCP)
- [ ] Call `POST /api/controls/training/start-v5` with auth to trigger training on Render's persistent disk
- [ ] Monitor logs for `[V5] Looking for global model at: /var/data/models/v5/global/...`
- [ ] Monitor logs for `[V5] Global model loaded from filesystem`
- [ ] Wait for training completion: `[V5] Global model saved to /var/data/models/v5/global/`
- [ ] Wait for next prediction cycle: confirm `[V5] Results: X LONG / Y SHORT / Z HOLD` where X+Y > 0
