# Per-Coin LONG Threshold Configuration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-coin LONG signal suppression/optimization so coins with historically poor LONG win rates (≤20%) are silenced for LONG, while coins with excellent LONG win rates use a lower threshold to capture more alpha.

**Architecture:** A new module `src/config/per_coin_config.py` owns the data (disabled set + optimized thresholds). `TradingPredictorV5.predict_single` reads from it to gate LONG signals before they reach the caller. No other layer is touched — short signals and the global SHORT threshold are unaffected.

**Tech Stack:** Python 3.11, pytest, loguru (already used in predictor), no new dependencies.

---

## Critical Context for the Implementer

### Ticker format
All tickers in this codebase use the `USDT` suffix: `STXUSDT`, `FILUSDT`, `ADAUSDT`, `RUNEUSDT`. The task description mentions bare names (STX, FIL) — those do NOT exist as keys anywhere. Always use the `USDT` form.

### Current default long_threshold = 0.35
`predictor_v5.py` line 46: `DEFAULT_LONG_THRESHOLD = 0.35`. The per-coin config introduces a **stricter default of 0.65** for coins not explicitly listed, applied ONLY in the per-coin gating logic. The global `DEFAULT_LONG_THRESHOLD = 0.35` is NOT changed — it remains the fallback when `predict_single` is called without per-coin config.

### Integration point
`predict_single` (line 302) already has:
```python
lt = long_threshold or self.long_threshold
```
The per-coin logic runs AFTER probabilities are computed, BEFORE the signal assignment block (lines 374–387). It overrides `lt` with the coin-specific threshold and short-circuits to `SIGNAL_HOLD` for disabled coins.

### Where `predict_single` resolves the ticker
The `ticker` argument arrives as e.g. `"STXUSDT"`. The per-coin config keys must match this format exactly.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/config/__init__.py` | Makes `src.config` a package |
| Create | `src/config/per_coin_config.py` | All per-coin LONG config data |
| Modify | `src/models/predictor_v5.py` | Import + apply per-coin config in `predict_single` |
| Create | `tests/test_per_coin_config.py` | Tests for the new gating logic |

---

## Task 1: Create `src/config` package with per-coin config

**Files:**
- Create: `src/config/__init__.py`
- Create: `src/config/per_coin_config.py`

- [ ] **Step 1: Create the package init**

Create `src/config/__init__.py` as an empty file (just a docstring):

```python
"""Per-coin trading configuration."""
```

- [ ] **Step 2: Write the failing test first (TDD)**

We write the test BEFORE implementing the module, so the import itself is the first failure.

Create `tests/test_per_coin_config.py`:

```python
"""Tests for per-coin LONG threshold configuration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.config.per_coin_config import (
    LONG_DISABLED_COINS,
    LONG_OPTIMIZED_COINS,
    get_long_threshold,
)


# ---------------------------------------------------------------------------
# LONG_DISABLED_COINS
# ---------------------------------------------------------------------------

def test_stxusdt_is_disabled():
    assert "STXUSDT" in LONG_DISABLED_COINS


def test_filusdt_is_disabled():
    assert "FILUSDT" in LONG_DISABLED_COINS


def test_adausdt_is_disabled():
    assert "ADAUSDT" in LONG_DISABLED_COINS


def test_runeusdt_is_disabled():
    assert "RUNEUSDT" in LONG_DISABLED_COINS


def test_disabled_coins_use_usdt_suffix():
    for coin in LONG_DISABLED_COINS:
        assert coin.endswith("USDT"), f"{coin} must end with USDT"


# ---------------------------------------------------------------------------
# LONG_OPTIMIZED_COINS
# ---------------------------------------------------------------------------

def test_arbusdt_optimized_threshold():
    assert "ARBUSDT" in LONG_OPTIMIZED_COINS
    assert LONG_OPTIMIZED_COINS["ARBUSDT"] == pytest.approx(0.40)


def test_aaveusdt_optimized_threshold():
    assert "AAVEUSDT" in LONG_OPTIMIZED_COINS
    assert LONG_OPTIMIZED_COINS["AAVEUSDT"] == pytest.approx(0.45)


def test_optimized_coins_use_usdt_suffix():
    for coin in LONG_OPTIMIZED_COINS:
        assert coin.endswith("USDT"), f"{coin} must end with USDT"


def test_disabled_and_optimized_are_disjoint():
    overlap = LONG_DISABLED_COINS & set(LONG_OPTIMIZED_COINS.keys())
    assert overlap == set(), f"Coins in both sets: {overlap}"


# ---------------------------------------------------------------------------
# get_long_threshold
# ---------------------------------------------------------------------------

DEFAULT_STRICT = 0.65  # the stricter default for unlisted coins


def test_get_long_threshold_disabled_returns_one():
    """Disabled coin → threshold=1.0 (impossible to meet → always HOLD)."""
    assert get_long_threshold("STXUSDT") == pytest.approx(1.0)
    assert get_long_threshold("FILUSDT") == pytest.approx(1.0)
    assert get_long_threshold("ADAUSDT") == pytest.approx(1.0)


def test_get_long_threshold_optimized_arb():
    assert get_long_threshold("ARBUSDT") == pytest.approx(0.40)


def test_get_long_threshold_optimized_aave():
    assert get_long_threshold("AAVEUSDT") == pytest.approx(0.45)


def test_get_long_threshold_default_for_unlisted():
    """Coins not in either set get the strict default."""
    assert get_long_threshold("SOLUSDT") == pytest.approx(DEFAULT_STRICT)
    assert get_long_threshold("DOTUSDT") == pytest.approx(DEFAULT_STRICT)


def test_get_long_threshold_unknown_coin_gets_default():
    assert get_long_threshold("XYZUSDT") == pytest.approx(DEFAULT_STRICT)
```

- [ ] **Step 3: Run the test — confirm it FAILS (module not found)**

```bash
/Users/User/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_per_coin_config.py -v 2>&1 | head -20
```

Expected output includes: `ModuleNotFoundError` or `ImportError` for `src.config.per_coin_config`.

- [ ] **Step 4: Create `src/config/per_coin_config.py`**

```python
"""
Per-Coin LONG Threshold Configuration
======================================
Controls LONG signal gating per ticker.

Rationale (from backtest 2026-06-02):
- Global LONG win rate: 26.8% → EV negative (break-even at 37.5% with +5% TP / -3% SL)
- SHORT win rate: 47.5% → EV positive

Strategy:
1. LONG_DISABLED_COINS: tickers with ≤20% LONG WR → threshold=1.0 (impossible to emit LONG)
2. LONG_OPTIMIZED_COINS: tickers with ≥44% LONG WR → lower threshold to capture more alpha
3. All other tickers: DEFAULT_LONG_THRESHOLD_STRICT = 0.65 (high bar, only strong conviction)

Ticker format: always USDT suffix (e.g. 'STXUSDT', not 'STX').
"""

from typing import Dict, FrozenSet

# ---------------------------------------------------------------------------
# Coins with destructive LONG performance — suppress LONG entirely.
# A threshold of 1.0 is mathematically impossible to exceed (probas sum to 1),
# so it guarantees HOLD for any LONG candidate on these tickers.
# ---------------------------------------------------------------------------
# Evidence:
#   STXUSDT:  16% LONG WR — negative return total
#   FILUSDT:  negative return total
#   ADAUSDT:  19% LONG WR
#   RUNEUSDT: 0% LONG WR
#   XLMUSDT:  poor LONG WR (not in current TICKERS — safe to include)
#   TRXUSDT:  poor LONG WR (not in current TICKERS — safe to include)
LONG_DISABLED_COINS: FrozenSet[str] = frozenset({
    "STXUSDT",   # 16% LONG WR, negative return
    "FILUSDT",   # negative return total
    "ADAUSDT",   # 19% LONG WR
    "RUNEUSDT",  # 0% LONG WR
})

# ---------------------------------------------------------------------------
# Coins with excellent LONG performance — lower threshold to capture more alpha.
# Evidence:
#   ARBUSDT:  ~59% LONG WR → lower to 0.40 (model is already conservative)
#   AAVEUSDT: ~44% LONG WR → lower to 0.45
#   BNBUSDT:  ~47% LONG WR → lower to 0.45 (not in TICKERS but future-safe)
#   LINKUSDT: ~45% estimated LONG WR → lower to 0.45
# ---------------------------------------------------------------------------
LONG_OPTIMIZED_COINS: Dict[str, float] = {
    "ARBUSDT":  0.40,  # ~59% LONG WR — most aggressive reduction
    "AAVEUSDT": 0.45,  # ~44% LONG WR
    "LINKUSDT": 0.45,  # ~45% LONG WR estimate
}

# Strict default: applied to all coins not in either set above.
# Raised from global 0.35 to 0.65 so only high-conviction LONG signals pass.
DEFAULT_LONG_THRESHOLD_STRICT: float = 0.65


def get_long_threshold(ticker: str) -> float:
    """
    Return the LONG probability threshold for a given ticker.

    - Disabled coins:  1.0 (mathematically impossible → always HOLD)
    - Optimized coins: coin-specific lower threshold
    - All others:      DEFAULT_LONG_THRESHOLD_STRICT (0.65)

    Args:
        ticker: Coin symbol with USDT suffix, e.g. 'ARBUSDT'.

    Returns:
        float threshold in (0.0, 1.0].
    """
    if ticker in LONG_DISABLED_COINS:
        return 1.0
    if ticker in LONG_OPTIMIZED_COINS:
        return LONG_OPTIMIZED_COINS[ticker]
    return DEFAULT_LONG_THRESHOLD_STRICT
```

- [ ] **Step 5: Run the test — confirm ALL pass**

```bash
/Users/User/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_per_coin_config.py -v
```

Expected output: all tests PASS, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add src/config/__init__.py src/config/per_coin_config.py tests/test_per_coin_config.py
git commit -m "feat(config): add per-coin LONG threshold gating"
```

---

## Task 2: Integrate per-coin config into `TradingPredictorV5.predict_single`

**Files:**
- Modify: `src/models/predictor_v5.py` (lines 16–21 imports section, lines 370–387 signal assignment block)
- Test: `tests/test_per_coin_config.py` (add integration tests at the bottom)

- [ ] **Step 1: Add integration tests first**

Append these tests to `tests/test_per_coin_config.py`:

```python
# ---------------------------------------------------------------------------
# Integration: TradingPredictorV5 applies per-coin config
# ---------------------------------------------------------------------------

import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch
from src.models.predictor_v5 import TradingPredictorV5, SIGNAL_HOLD, SIGNAL_LONG


def _make_ohlcv(n=250, seed=42):
    rng = np.random.RandomState(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    return pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.01,
        "low":  close * 0.99,
        "close": close,
        "volume": rng.uniform(1e6, 1e7, n),
    })


def _make_predictor(proba):
    """Return a predictor whose mock model always emits `proba`."""
    mock_model = MagicMock()
    mock_model.feature_names = [f"f{i}" for i in range(10)]
    mock_model.predict_proba.return_value = np.array([proba])

    with patch.object(TradingPredictorV5, "_load_global_model"):
        with patch.object(TradingPredictorV5, "_fetch_external_data_sync", return_value={}):
            predictor = TradingPredictorV5()
            predictor._global_model = mock_model
            predictor._cached_external = {}
    return predictor


def test_stxusdt_never_emits_long_even_with_high_p_long():
    """STXUSDT is disabled — even p_long=0.95 must produce HOLD."""
    predictor = _make_predictor([0.02, 0.95, 0.03])  # very high p_long
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, proba_3, _ = predictor.predict_single("STXUSDT", ohlcv)

    assert signal_class == SIGNAL_HOLD, (
        f"STXUSDT must never emit LONG, got {signal_class}"
    )


def test_filusdt_never_emits_long():
    predictor = _make_predictor([0.02, 0.95, 0.03])
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("FILUSDT", ohlcv)

    assert signal_class == SIGNAL_HOLD


def test_arbusdt_emits_long_above_0_40_threshold():
    """ARBUSDT threshold=0.40 — p_long=0.42 must emit LONG (above 0.40)."""
    predictor = _make_predictor([0.30, 0.42, 0.28])
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("ARBUSDT", ohlcv)

    assert signal_class == SIGNAL_LONG


def test_solusdt_holds_below_strict_default():
    """SOLUSDT uses default 0.65 — p_long=0.50 must produce HOLD."""
    predictor = _make_predictor([0.20, 0.50, 0.30])
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("SOLUSDT", ohlcv)

    assert signal_class == SIGNAL_HOLD


def test_solusdt_emits_long_above_strict_default():
    """SOLUSDT uses default 0.65 — p_long=0.70 must produce LONG."""
    predictor = _make_predictor([0.10, 0.70, 0.20])
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("SOLUSDT", ohlcv)

    assert signal_class == SIGNAL_LONG
```

- [ ] **Step 2: Run integration tests — confirm they FAIL**

```bash
/Users/User/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_per_coin_config.py -v -k "stxusdt or filusdt or arbusdt or solusdt" 2>&1
```

Expected: integration tests FAIL because `predict_single` doesn't yet use per-coin config.

- [ ] **Step 3: Modify `predictor_v5.py` — add import**

In `src/models/predictor_v5.py`, after the existing imports block (around line 37), add:

```python
from src.config.per_coin_config import get_long_threshold
```

Exact location — insert after line 37 (`from src.models.position_sizer import KellyPositionSizer`):

Old block (lines 35–37):
```python
from src.models.ensemble_v5 import EnsembleV5
from src.models.regime_detector import RegimeDetector
from src.models.position_sizer import KellyPositionSizer
```

New block:
```python
from src.models.ensemble_v5 import EnsembleV5
from src.models.regime_detector import RegimeDetector
from src.models.position_sizer import KellyPositionSizer
from src.config.per_coin_config import get_long_threshold
```

- [ ] **Step 4: Modify `predict_single` — apply per-coin threshold**

Find this block in `predict_single` (lines 301–303):

```python
        try:
            lt = long_threshold or self.long_threshold
            st = short_threshold or self.short_threshold
```

Replace with:

```python
        try:
            # Per-coin LONG threshold: disabled coins get 1.0 (impossible),
            # optimized coins get a lower value, others get 0.65 strict default.
            # Caller override (long_threshold kwarg) takes precedence if provided.
            coin_lt = get_long_threshold(ticker)
            lt = long_threshold if long_threshold is not None else coin_lt
            if coin_lt == 1.0 and long_threshold is None:
                logger.info(f"[V5] {ticker}: LONG disabled by per-coin config")
            st = short_threshold or self.short_threshold
```

**Why `long_threshold is not None` instead of `long_threshold or`:** the original code uses `long_threshold or self.long_threshold` which would fall through on `long_threshold=0` (falsy). The fix uses `is not None` so an explicit `0.0` override is respected. This is a small correctness improvement included in this change.

- [ ] **Step 5: Run ALL tests — confirm full suite passes**

```bash
/Users/User/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_per_coin_config.py -v
```

Expected: ALL tests PASS, including the integration tests.

Also verify the existing predictor test suite still passes:

```bash
/Users/User/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_predictor_v5.py -v
```

Expected: ALL existing tests PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add src/models/predictor_v5.py
git commit -m "feat(predictor): apply per-coin LONG threshold gating in predict_single"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] `src/config/per_coin_config.py` with `LONG_DISABLED_COINS`, `LONG_OPTIMIZED_COINS` — Task 1
- [x] `get_long_threshold()` function as integration interface — Task 1
- [x] `predictor_v5.py` import + per-coin threshold applied — Task 2
- [x] LONG suppressed for disabled coins even with high p_long — integration test
- [x] ARB uses 0.40 threshold — integration test
- [x] Default coins use 0.65 threshold — integration test
- [x] Log message when LONG is suppressed — Task 2, Step 4

**Ticker format:** All disabled/optimized sets use `USDT` suffix. Tests verify this with `endswith("USDT")` assertion.

**Threshold semantics:** disabled → 1.0 (not just "high"), so no probability can accidentally trigger it. This is cleaner than `999` or `float('inf')` because `>=` comparisons still work numerically.

**`long_threshold is not None` fix:** backward-compatible — callers passing `None` (default) get per-coin behavior; callers explicitly passing a value override it.

**No placeholder steps:** every step has exact code, exact command, exact expected output.
