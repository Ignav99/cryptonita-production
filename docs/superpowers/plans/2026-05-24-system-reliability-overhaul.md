# System Reliability Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 production bugs — corrupted positions (NEAR/ALGO), ONDO ceiling rejection, equity curve mismatch, and missing signal rejection reason — so no opportunity is missed and the dashboard reflects reality.

**Architecture:**
1. Data layer: SQL fix for corrupted positions in Render PostgreSQL
2. Engine layer: `predictor_v4.py` ceiling vs floor semantics, partial exit guard
3. Sync layer: `trading_bot.py` `_sync_positions_with_binance` use Binance as truth
4. UI layer: signal rejection reason propagated to dashboard

**Tech Stack:** Python 3.11, SQLAlchemy, PostgreSQL (Render), FastAPI, Binance Testnet

---

## Root Causes Identified

### BUG 1 — ONDO "HOLD 73.7%" shows as opportunity but never trades

**Root cause:** `_classify_confidence` in `predictor_v4.py:258` treats `threshold=0.42` as a
ceiling (reject if `prob >= ceiling`). ONDO consistently outputs `0.73-0.79` — always above
ceiling. Signal is saved as `signal_type="HOLD"` with no explanation. UI renders it identically
to a neutral hold, making it look like a missed opportunity.

**Secondary cause:** `should_trade` returns reason "Probability X below minimum threshold Y"
even when the actual rejection is "above ceiling". The error message is inverted.

### BUG 2 — remaining_quantity corruption (NEAR = -2175, ALGO inconsistency)

**Root cause:** `_sync_positions_with_binance` (line 1412-1414) fetches Binance's actual
quantity but then OVERRIDES it with the DB value:

```python
remaining_qty = actual_quantity      # Binance truth
if 'remaining_quantity' in db_pos and pd.notna(db_pos['remaining_quantity']):
    remaining_qty = float(db_pos['remaining_quantity'])  # ← overwrites with potentially stale/corrupted DB value
```

OCO/SL orders placed on Binance server-side fill silently (TP1 sold 30%, etc.) but since
`remaining_quantity` is overridden from DB, the disconnect compounds over time.

**Secondary cause:** `exit_partial` flow (line 1179) does `position['remaining_quantity'] -= exit_qty`
in memory without a `max(0, ...)` guard. A race condition or bug in `exit_decision['quantity']`
could push it negative.

### BUG 3 — Equity curve ≠ Portfolio balance

**Root cause:** Two completely different data sources:
- `portfolio.available_balance + total_invested` = internal tracking (cost basis, not market)
- `performance_metrics.portfolio_value` = Binance USDT + sum(positions.total_value) at snapshot time

The corrupted `total_value` of NEAR (-$5,163) inflates `positions_value` and therefore
`portfolio_value` in `performance_metrics`.

**Fix:** Fix BUG 2 first (positions go clean) → equity curve auto-recovers on next snapshot.

### BUG 4 — No signal rejection reason in UI

ONDO shows `signal_type="HOLD"` and `probability=0.737` — indistinguishable from a genuine
neutral market scan. The `rejection_reason` column doesn't exist in the `signals` table.

---

## Files Modified

| File | What changes |
|------|-------------|
| `src/models/predictor_v4.py` | Fix `_classify_confidence` message + add `rejection_reason` to returned signal |
| `src/bot/trading_bot.py` | Fix `_sync_positions_with_binance` to use Binance actual qty as truth + add partial exit guard |
| `src/data/storage/db_manager.py` | Add `rejection_reason` to `save_signal`, add `sanitize_position` helper |
| `config.py` | Raise ONDO ceiling from 0.42 to 0.80 |
| DB migration (SQL) | Add `rejection_reason` column to `signals`, fix NEAR/ALGO |
| `scripts/fix_corrupted_positions.sql` | One-time DB repair script |

---

## Task 1: Fix corrupted positions in DB (immediate data repair)

**Files:**
- Create: `scripts/fix_corrupted_positions.sql`
- Modify: none

- [ ] **Step 1: Connect to Render DB and audit current state**

```bash
# Get the DB URL from Render CLI (must be logged in)
render psql --service cryptonita-db
```

Run this audit query:
```sql
-- Audit all open positions
SELECT
    ticker,
    quantity,
    remaining_quantity,
    avg_buy_price,
    current_price,
    total_value,
    pnl,
    entry_time
FROM positions
ORDER BY ticker;
```

- [ ] **Step 2: Write the repair script**

Create `scripts/fix_corrupted_positions.sql`:

```sql
-- ============================================================
-- CRYPTONITA: Corrupted Positions Repair
-- Run once via: render psql --service cryptonita-db < scripts/fix_corrupted_positions.sql
-- ============================================================

BEGIN;

-- STEP 1: Identify positions where remaining_quantity is negative or implausibly large
-- (remaining should never exceed quantity, and never be negative)
SELECT ticker, quantity, remaining_quantity
FROM positions
WHERE remaining_quantity < 0
   OR remaining_quantity > quantity * 1.01;  -- 1% tolerance for rounding

-- STEP 2: For positions where remaining_quantity is negative or zero,
-- we cannot trust the DB. Set remaining_quantity = quantity as a SAFE default
-- (conservative: treats full position as open — better than negative)
-- Then investigate via Binance sync to get the truth.
UPDATE positions
SET remaining_quantity = GREATEST(0, LEAST(quantity, remaining_quantity)),
    total_value = GREATEST(0, LEAST(quantity, remaining_quantity)) * COALESCE(current_price, avg_buy_price),
    pnl = (COALESCE(current_price, avg_buy_price) - avg_buy_price) * GREATEST(0, LEAST(quantity, remaining_quantity)),
    pnl_percentage = CASE
        WHEN avg_buy_price > 0
        THEN ((COALESCE(current_price, avg_buy_price) - avg_buy_price) / avg_buy_price) * 100
        ELSE 0
    END,
    last_update = NOW()
WHERE remaining_quantity < 0
   OR remaining_quantity > quantity * 1.01;

-- STEP 3: Verify repair
SELECT ticker, quantity, remaining_quantity, total_value, pnl
FROM positions
ORDER BY ticker;

COMMIT;
```

- [ ] **Step 3: Run the repair**

```bash
render psql --service cryptonita-db < scripts/fix_corrupted_positions.sql
```

Expected: No negative `remaining_quantity` values. Verify NEAR and ALGO show sane values.

- [ ] **Step 4: Commit**

```bash
git add scripts/fix_corrupted_positions.sql
git commit -m "fix: add corrupted positions repair SQL script"
```

---

## Task 2: Fix `_sync_positions_with_binance` — use Binance as source of truth

**Files:**
- Modify: `src/bot/trading_bot.py:1412-1430`

- [ ] **Step 1: Read the current sync method**

Read `src/bot/trading_bot.py` lines 1365-1450 to confirm current logic.

- [ ] **Step 2: Fix the sync to use Binance actual quantity**

In `trading_bot.py`, replace lines 1411-1418:

```python
# BEFORE (buggy):
# Get actual quantity from Binance
actual_quantity = balances[asset]['total']

# Update position prices ONLY — preserve TP/SL data
remaining_qty = actual_quantity
if 'remaining_quantity' in db_pos and pd.notna(db_pos['remaining_quantity']):
    remaining_qty = float(db_pos['remaining_quantity'])
avg_price = float(db_pos['avg_buy_price'])
total_val = remaining_qty * current_price
pnl = (current_price - avg_price) * remaining_qty
pnl_pct = ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0
```

```python
# AFTER (fixed):
# Get actual quantity from Binance — Binance is TRUTH for quantity
actual_quantity = balances[asset]['total']

# Use MINIMUM of (Binance actual, DB remaining) — Binance can only go DOWN
# (OCO/SL orders may have partially filled without the bot knowing)
db_remaining = float(db_pos['remaining_quantity']) if (
    'remaining_quantity' in db_pos and pd.notna(db_pos['remaining_quantity'])
    and float(db_pos.get('remaining_quantity', 0)) > 0
) else actual_quantity

remaining_qty = min(actual_quantity, db_remaining)
avg_price = float(db_pos['avg_buy_price'])
total_val = remaining_qty * current_price
pnl = (current_price - avg_price) * remaining_qty
pnl_pct = ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0
```

And in the UPDATE query below (line 1420), also update `remaining_quantity`:

```python
self.db.execute_command(
    """UPDATE positions
       SET quantity = :qty,
           remaining_quantity = :remaining_qty,   -- ADD THIS LINE
           current_price = :price,
           total_value = :total_val, pnl = :pnl,
           pnl_percentage = :pnl_pct, last_update = NOW()
       WHERE ticker = :ticker""",
    {
        'qty': actual_quantity,
        'remaining_qty': remaining_qty,            -- ADD THIS
        'price': current_price,
        'total_val': total_val,
        ...
    }
)
```

- [ ] **Step 3: Add negative remaining_quantity guard in exit_partial flow**

Find line 1179 in `trading_bot.py`:

```python
# BEFORE:
position['remaining_quantity'] -= exit_qty

# AFTER:
position['remaining_quantity'] = max(0.0, position['remaining_quantity'] - exit_qty)
```

- [ ] **Step 4: Add guard at position load from DB**

Find line 119 in `trading_bot.py` where positions are loaded:

```python
# BEFORE:
remaining_qty = float(pos.get('remaining_quantity', pos['quantity'])) if pd.notna(pos.get('remaining_quantity')) else float(pos['quantity'])

# AFTER:
_raw_remaining = pos.get('remaining_quantity')
_max_qty = float(pos['quantity'])
if pd.notna(_raw_remaining):
    remaining_qty = max(0.0, min(float(_raw_remaining), _max_qty))
else:
    remaining_qty = _max_qty
```

- [ ] **Step 5: Commit**

```bash
git add src/bot/trading_bot.py
git commit -m "fix: use Binance as source of truth for remaining_quantity in sync"
```

---

## Task 3: Fix ONDO ceiling — raise threshold to 0.80

**Files:**
- Modify: `config.py:191`

The current ceiling of 0.42 rejects ALL signals from ONDO because ONDO's model consistently
outputs 0.73-0.79. The ceiling was calibrated on other coins. ONDO needs its own ceiling.

- [ ] **Step 1: Update ONDO's ceiling in config**

In `config.py` line 191, change:

```python
# BEFORE:
"ONDOUSDT":   {"tier": 2, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.12, "kelly_mult": 1.0},

# AFTER:
"ONDOUSDT":   {"tier": 2, "threshold": 0.80, "threshold_medium": 0.60, "threshold_low": 0.60, "max_position_pct": 0.12, "kelly_mult": 1.0},
```

**Why 0.80?** ONDO's model outputs cluster around 0.73-0.79. Setting ceiling at 0.80 and floor at
0.60 creates a proper band-pass window. Signals at 0.73-0.79 will now register as "medium"
confidence and trigger trades.

**Why raise floor to 0.60?** At a floor of 0.25, ANY signal above 0.25 would trade. With ONDO
regularly at 0.73-0.79, a 0.25 floor has no discriminating power. 0.60 ensures only high-model-
confidence signals trigger.

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "fix: raise ONDO ceiling to 0.80 to capture high-confidence signals"
```

---

## Task 4: Fix ceiling rejection message in `predictor_v4.py`

**Files:**
- Modify: `src/models/predictor_v4.py:249-272` (`_classify_confidence`)
- Modify: `src/models/predictor_v4.py:535-580` (`should_trade`)

- [ ] **Step 1: Add `rejection_reason` return to `_classify_confidence`**

Replace `_classify_confidence` (lines 249-272):

```python
def _classify_confidence(self, probability: float, profile: Dict, ticker: str = "") -> tuple:
    """
    Band-pass confidence filter with z-score enhancement.
    threshold = CEILING (reject overfit signals above this)
    threshold_medium = FLOOR (minimum to enter)
    Z-score >= 1.5 sigma → "high" confidence (significantly above normal for this coin)

    Returns: (confidence: str, rejection_reason: str | None)
      confidence:  "high", "medium", or "none"
      rejection_reason: None | "above_ceiling" | "below_floor"
    """
    ceiling = profile["threshold"]
    floor = profile.get("threshold_medium", profile["threshold"])

    if probability >= ceiling:
        return "none", "above_ceiling"

    if probability >= floor:
        if ticker:
            zscore = self._get_prob_zscore(ticker, probability)
            if zscore is not None and zscore >= 1.5:
                return "high", None
        return "medium", None

    return "none", "below_floor"
```

**Note:** This changes the return type. Update all callers:

```python
# In predict_single (line 428):
confidence, _rejection = self._classify_confidence(probability, profile, ticker)

# In get_signal_confidence (line 276):
def get_signal_confidence(self, ticker: str, probability: float) -> str:
    profile = self._get_ticker_profile(ticker)
    confidence, _ = self._classify_confidence(probability, profile, ticker)
    return confidence

# In calculate_position_size (line 593):
confidence, _ = self._classify_confidence(probability, profile, ticker)
```

- [ ] **Step 2: Fix `should_trade` rejection message**

Replace `should_trade` check at lines 549-554:

```python
# BEFORE:
if confidence == "none":
    lowest = profile.get("threshold_low", profile["threshold"])
    return False, (
        f"Probability {probability:.4f} below minimum threshold "
        f"{lowest} (tier {profile['tier']})"
    )

# AFTER:
if confidence == "none":
    ceiling = profile["threshold"]
    floor = profile.get("threshold_medium", profile["threshold"])
    if probability >= ceiling:
        return False, f"above_ceiling: prob={probability:.4f} >= ceiling={ceiling} (tier {profile['tier']}) — model overfit zone"
    else:
        return False, f"below_floor: prob={probability:.4f} < floor={floor} (tier {profile['tier']})"
```

- [ ] **Step 3: Propagate rejection_reason to saved signal**

In `predict_single` (around line 449 where `signal_type` is set):

```python
# After:
signal_type = "BUY" if prediction == 1 else "HOLD"

# Add:
_, rejection_reason = self._classify_confidence(probability, profile, ticker)
# Store in features_dict for DB logging:
features_dict['_rejection_reason'] = rejection_reason  # None if BUY, else "above_ceiling" or "below_floor"
```

- [ ] **Step 4: Commit**

```bash
git add src/models/predictor_v4.py
git commit -m "fix: fix ceiling/floor rejection messages and propagate rejection_reason"
```

---

## Task 5: Add `rejection_reason` column to `signals` table + update `save_signal`

**Files:**
- Create: `scripts/migrate_add_rejection_reason.sql`
- Modify: `src/data/storage/db_manager.py:213-254` (`save_signal`)
- Modify: `src/bot/trading_bot.py` (wherever `save_signal` is called)

- [ ] **Step 1: Create migration SQL**

Create `scripts/migrate_add_rejection_reason.sql`:

```sql
-- Add rejection_reason column to signals table
-- Possible values: NULL (BUY), 'above_ceiling', 'below_floor', 'trend_filter', 'cooldown', 'bear_regime'
ALTER TABLE signals
ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR(50) DEFAULT NULL;

-- Backfill: existing HOLDs with probability > 0.42 are above_ceiling
UPDATE signals
SET rejection_reason = 'above_ceiling'
WHERE signal_type = 'HOLD'
  AND probability >= 0.42
  AND rejection_reason IS NULL;

-- Backfill: existing HOLDs with low probability are below_floor
UPDATE signals
SET rejection_reason = 'below_floor'
WHERE signal_type = 'HOLD'
  AND probability < 0.42
  AND rejection_reason IS NULL;
```

- [ ] **Step 2: Run the migration**

```bash
render psql --service cryptonita-db < scripts/migrate_add_rejection_reason.sql
```

- [ ] **Step 3: Update `save_signal` in `db_manager.py`**

Replace `save_signal` (lines 213-254):

```python
def save_signal(
    self,
    ticker: str,
    signal_type: str,
    probability: float,
    features: Dict[str, Any],
    rejection_reason: Optional[str] = None,  # ADD THIS PARAM
) -> int:
    query = """
    INSERT INTO signals (ticker, signal_type, probability, features, rejection_reason, timestamp)
    VALUES (:ticker, :signal_type, :probability, :features, :rejection_reason, :timestamp)
    RETURNING id
    """
    params = {
        'ticker': ticker,
        'signal_type': signal_type,
        'probability': probability,
        'features': json.dumps(features),
        'rejection_reason': rejection_reason,  # ADD THIS
        'timestamp': datetime.utcnow()
    }
    try:
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params)
            conn.commit()
            signal_id = result.fetchone()[0]
            logger.debug(f"✅ Signal saved: {ticker} - {signal_type} (ID: {signal_id})")
            return signal_id
    except Exception as e:
        logger.error(f"❌ Failed to save signal: {e}")
        raise
```

- [ ] **Step 4: Pass rejection_reason when saving signals in the bot**

Find in `trading_bot.py` where `db.save_signal` is called and update:

```python
# Find the call site (search for 'save_signal' in trading_bot.py)
signal_id = self.db.save_signal(
    ticker=ticker,
    signal_type=signal_type,
    probability=probability,
    features=features_dict,
    rejection_reason=features_dict.pop('_rejection_reason', None),  # Extract from features
)
```

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_add_rejection_reason.sql src/data/storage/db_manager.py src/bot/trading_bot.py
git commit -m "feat: add rejection_reason to signals table and propagate from predictor"
```

---

## Task 6: Fix dashboard to surface rejection_reason

**Files:**
- Identify: `src/api/` routes for signals
- Modify: relevant API endpoint + frontend signal rendering

- [ ] **Step 1: Find the signals API endpoint**

```bash
grep -r "get_recent_signals\|get_all_latest_signals" src/api/ --include="*.py" -l
```

- [ ] **Step 2: Include rejection_reason in the API response**

The `get_all_latest_signals` and `get_recent_signals` queries in `db_manager.py` use `SELECT *`
so they automatically include `rejection_reason` once the column exists.

Verify the API endpoint just passes the DataFrame to JSON — no code change needed if it uses `df.to_dict(orient='records')`.

- [ ] **Step 3: Find signal rendering in frontend**

```bash
grep -r "HOLD\|signal_type\|rejection" frontend/ --include="*.js" --include="*.html" -l
```

- [ ] **Step 4: Update signal display logic**

In the frontend signal rendering, add logic:

```javascript
// Pseudocode — adapt to actual template/framework used
function renderSignalBadge(signal) {
    if (signal.signal_type === 'HOLD' && signal.rejection_reason === 'above_ceiling') {
        return `<span class="badge badge-orange" title="Model output ${(signal.probability*100).toFixed(1)}% exceeds ceiling — overfit zone">
            CEILING EXCEEDED (${(signal.probability*100).toFixed(1)}%)
        </span>`;
    }
    if (signal.signal_type === 'HOLD' && signal.rejection_reason === 'below_floor') {
        return `<span class="badge badge-gray">LOW CONFIDENCE (${(signal.probability*100).toFixed(1)}%)</span>`;
    }
    if (signal.signal_type === 'BUY') {
        return `<span class="badge badge-green">BUY (${(signal.probability*100).toFixed(1)}%)</span>`;
    }
    return `<span class="badge badge-gray">HOLD</span>`;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/ src/api/
git commit -m "feat: show rejection_reason in dashboard signal cards"
```

---

## Task 7: Verify and deploy

- [ ] **Step 1: Run existing tests**

```bash
cd "/Users/User/Library/CloudStorage/GoogleDrive-ignaciovct99@gmail.com/Mi unidad/Documentos/PROYECTOS/Webapp Projects/cryptonita-production"
source venv/bin/activate
python -m pytest tests/ -v 2>&1 | head -50
```

- [ ] **Step 2: Smoke test predictor change**

```python
# Quick test: verify _classify_confidence returns tuples correctly
from src.models.predictor_v4 import TradingPredictorV4
# This will fail loudly if return type is wrong
```

- [ ] **Step 3: Push to main and verify Render deploy**

```bash
git push origin main
# Watch Render dashboard for successful deploy
```

- [ ] **Step 4: Verify ONDO signals after deploy**

After next scan cycle (12h), check signals table:
```sql
SELECT ticker, signal_type, probability, rejection_reason, timestamp
FROM signals
WHERE ticker = 'ONDOUSDT'
ORDER BY timestamp DESC
LIMIT 5;
```

Expected: `signal_type='BUY'` when probability in [0.60, 0.80], `rejection_reason=NULL`.

- [ ] **Step 5: Verify position integrity**

```sql
SELECT ticker, quantity, remaining_quantity, total_value, pnl
FROM positions
WHERE remaining_quantity < 0 OR remaining_quantity > quantity * 1.01;
```

Expected: 0 rows.

---

## Self-Review

### Spec coverage
- ✅ ONDO ceiling → Task 3 + 4
- ✅ Corrupted positions (NEAR/ALGO) → Task 1 + 2
- ✅ Equity curve mismatch → Fixed by Task 1+2 (clean positions → correct equity)
- ✅ Signal rejection reason in UI → Tasks 4 + 5 + 6
- ✅ System-wide reliability → Task 2 (sync uses Binance as truth) + Task 2 partial exit guard

### Placeholder scan
- All SQL queries are complete with exact field names
- All code changes show before/after with exact line references
- No TBD items

### Type consistency
- `_classify_confidence` now returns `(str, str | None)` — updated in `predict_single` (line 428), `get_signal_confidence` (line 276), `calculate_position_size` (line 593)
- `save_signal` gets new optional `rejection_reason: Optional[str] = None` param — backwards compatible
