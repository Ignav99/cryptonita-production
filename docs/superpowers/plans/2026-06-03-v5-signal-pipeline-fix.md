# V5 Signal Pipeline Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 critical bugs that prevent V5 from generating and displaying signals on Render.

**Architecture:** The fix touches config, DB queries, training loop, and soft-reset. No new files — pure bug fixes across 4 existing files.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Pydantic-settings, PostgreSQL

---

## Root Cause Analysis

### Bug 1 — CRITICAL: Path mismatch between trainer (saves) and predictor (loads)
- `PerCoinModelStore` reads `V5_MODEL_DIR` from `os.environ` directly → uses `/var/data/models/v5` ✓
- `TradingPredictorV5` reads `getattr(settings, "V5_MODEL_DIR", fallback)` → `V5_MODEL_DIR` is NOT in Pydantic Settings → falls back to `"PRODUCTION_SYSTEM/models/v5"` ✗
- **Result:** Trainer saves to `/var/data/models/v5/global`, predictor looks in `./PRODUCTION_SYSTEM/models/v5/global` — never finds it → **always HOLD**

### Bug 2 — CRITICAL: Signal probability filter 0.60 hides all V5 signals
- `get_recent_signals(min_probability=0.60)` — V5 signals have p_long/p_short in range 0.35–0.55
- All real signals get filtered → dashboard shows 0 signals

### Bug 3 — Signal stats hardcoded for 'BUY' (V4 legacy)
- `get_signals_stats` counts `signal_type = 'BUY'` — V5 uses 'LONG'/'SHORT'
- `buy_count_7d` always 0 for all coins

### Bug 4 — Soft reset doesn't clear training_log → training skipped for 7 days
- `training_log` table persists across soft resets
- If V4 training was logged within 7 days, V5 training is SKIPPED silently
- Bot runs with no model indefinitely

---

## Files Modified

| File | What changes |
|------|-------------|
| `config.py` | Add `V5_MODEL_DIR` as Pydantic Settings field |
| `src/data/storage/db_manager.py` | Fix probability threshold + fix signal_type='BUY' |
| `src/bot/trading_bot.py` | Trigger immediate scan after training + reduce scan interval to 1h |
| `src/api/routes/controls.py` | Clear training_log in soft-reset |

---

## Task 1: Fix V5_MODEL_DIR in config.py

**Files:**
- Modify: `config.py:263` (after V4_MODEL_DIR line)

- [ ] **Step 1: Add V5_MODEL_DIR field to Settings**

In `config.py`, find the MODEL CONFIGURATION section. After line `V4_MODEL_DIR: str = str(PROJECT_ROOT / "PRODUCTION_SYSTEM/models/v4")`, add:

```python
V5_MODEL_DIR: str = Field(default="PRODUCTION_SYSTEM/models/v5", env="V5_MODEL_DIR")
```

The section should look like:
```python
USE_V4_MODEL: bool = Field(default=True, env="USE_V4_MODEL")
V4_MODEL_DIR: str = str(PROJECT_ROOT / "PRODUCTION_SYSTEM/models/v4")
V5_MODEL_DIR: str = Field(default="PRODUCTION_SYSTEM/models/v5", env="V5_MODEL_DIR")
KELLY_FRACTION: float = Field(default=0.25, env="KELLY_FRACTION")
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "fix: add V5_MODEL_DIR to Pydantic Settings so predictor reads correct env path"
```

---

## Task 2: Fix signal probability threshold and BUY→LONG/SHORT in db_manager.py

**Files:**
- Modify: `src/data/storage/db_manager.py:262` (get_recent_signals)
- Modify: `src/data/storage/db_manager.py:308` (get_signals_stats)

- [ ] **Step 1: Fix get_recent_signals default threshold**

Change `min_probability: float = 0.60` to `min_probability: float = 0.0` in `get_recent_signals`.

The function signature should become:
```python
def get_recent_signals(self, limit: int = 50, min_probability: float = 0.0, days: int = 7) -> pd.DataFrame:
```

- [ ] **Step 2: Fix get_signals_stats to count LONG and SHORT (not BUY)**

In `get_signals_stats`, replace the query. The current query has:
```sql
COUNT(*) FILTER (WHERE signal_type = 'BUY') as buy_count,
COUNT(*) FILTER (WHERE signal_type = 'HOLD') as hold_count
```

Replace with:
```sql
COUNT(*) FILTER (WHERE signal_type IN ('BUY', 'LONG')) as buy_count,
COUNT(*) FILTER (WHERE signal_type = 'SHORT') as short_count,
COUNT(*) FILTER (WHERE signal_type = 'HOLD') as hold_count
```

- [ ] **Step 3: Commit**

```bash
git add src/data/storage/db_manager.py
git commit -m "fix: lower signal probability threshold to 0.0 and add LONG/SHORT to stats query"
```

---

## Task 3: Add immediate scan trigger after training + reduce scan interval

**Files:**
- Modify: `src/bot/trading_bot.py:1696-1700` (after _load_global_model call)
- Modify: `src/bot/trading_bot.py:99` (scan_interval_hours default)

- [ ] **Step 1: Reduce default scan interval from 6h to 1h**

In `trading_bot.py`, find:
```python
"scan_interval_hours": 6,
```
Change to:
```python
"scan_interval_hours": 1,
```

- [ ] **Step 2: Add immediate scan trigger after V5 model loads**

After training completes and `_load_global_model()` is called (lines 1698-1700), add a flag to trigger immediate scan:

Find this block:
```python
if result is not None and hasattr(self.predictor, '_load_global_model'):
    self.predictor._load_global_model()
    logger.success("V5 global model reloaded after training")
```

Replace with:
```python
if result is not None and hasattr(self.predictor, '_load_global_model'):
    self.predictor._load_global_model()
    logger.success("V5 global model reloaded after training")
    # Trigger immediate scan so signals appear right after first training
    logger.info("[V5] Training complete — triggering immediate market scan...")
    try:
        await self._scan_market()
    except Exception as scan_err:
        logger.error(f"Post-training scan failed: {scan_err}")
```

- [ ] **Step 3: Commit**

```bash
git add src/bot/trading_bot.py
git commit -m "fix: reduce scan interval to 1h + trigger immediate scan after V5 training completes"
```

---

## Task 4: Clear training_log in soft-reset

**Files:**
- Modify: `src/api/routes/controls.py:439-458` (soft_reset body)

- [ ] **Step 1: Add training_log deletion to soft_reset**

In `soft_reset`, within the `with db.engine.connect() as conn:` block, after `conn.execute(text("DELETE FROM signals"))` add:

```python
# Clear training log so V5 retrains immediately on next startup
try:
    conn.execute(text("DELETE FROM training_log"))
except Exception:
    pass  # Table might not exist yet
```

The block should look like:
```python
with db.engine.connect() as conn:
    conn.execute(text("UPDATE trades SET signal_id = NULL WHERE signal_id IS NOT NULL"))
    conn.execute(text("DELETE FROM positions"))
    conn.execute(text("DELETE FROM signals"))
    # Clear training log so V5 retrains immediately after soft reset
    try:
        conn.execute(text("DELETE FROM training_log"))
    except Exception:
        pass

    conn.execute(text("""
        UPDATE portfolio ...
    """), ...)
```

- [ ] **Step 2: Commit**

```bash
git add src/api/routes/controls.py
git commit -m "fix: clear training_log on soft-reset so V5 auto-trains immediately after reset"
```

---

## Task 5: Push and verify on Render

- [ ] **Step 1: Push all commits**

```bash
git push origin main
```

- [ ] **Step 2: Wait for Render deploy (~2-3 min)**

Check Render logs for:
```
✅ Build completed successfully!
🌐 Starting API server...
```

- [ ] **Step 3: Soft-reset to clear old data and training_log**

```bash
TOKEN=$(curl -s -X POST https://cryptonita-production.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"cryptonita2025"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST https://cryptonita-production.onrender.com/api/controls/soft-reset \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

- [ ] **Step 4: Start bot**

```bash
curl -s -X POST https://cryptonita-production.onrender.com/api/controls/start \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

- [ ] **Step 5: Verify training starts in Render logs**

Look for within 5-10 minutes of start:
```
Starting V5 auto-training cycle (global model)...
[V5] Training global model on 47 coins...
```

- [ ] **Step 6: Verify signals appear after training (~15-30 min)**

Look for:
```
[V5] Global model trained on X coins
V5 global model reloaded after training
[V5] Training complete — triggering immediate market scan...
MARKET SCAN - CYCLE #2
📊 Signals: X LONG / Y SHORT / Z HOLD / 47 total
```

---

## Expected Result

After these fixes:
1. V5 trains on startup (no model exists, training_log cleared)
2. Model saves to `/var/data/models/v5/global` (persistent disk)
3. Predictor loads from same path (now reads env var correctly)
4. Immediate scan runs after training → first LONG/SHORT signals appear in dashboard
5. Dashboard shows signals with p >= 0.35 (not filtered by 0.60 threshold)
6. Stats show correct LONG/SHORT counts
7. Subsequent scans every 1h (not 6h)
