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
