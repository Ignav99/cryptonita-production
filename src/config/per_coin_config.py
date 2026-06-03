"""
Per-Coin LONG / SHORT Threshold Configuration
==============================================
Controls LONG and SHORT signal gating per ticker.

Break-even analysis (TP=+5% / SL=-3%):
  Break-even WR = SL / (TP + SL) = 3 / 8 = 37.5%
  Any coin with observed WR < 37.5% has negative EV per trade.

LONG configuration (from backtest 2026-06-02 pass 2):
- Break-even LONG WR = 37.5%
- Global LONG WR: 26.8% → EV negative ❌
- Only ARB has confirmed LONG edge (58.4% WR)
- Strategy: disable LONG on confirmed EV-negative coins, lower threshold for ARB

SHORT configuration (from backtest 2026-06-03):
- Break-even SHORT WR = 37.5%
- Global SHORT WR: 47.5% → EV positive ✅
- 4 coins have SHORT WR < break-even and must be disabled
- Strategy: disable SHORT on confirmed EV-negative coins

Ticker format: always USDT suffix (e.g. 'STXUSDT', not 'STX').
"""

from typing import Dict, FrozenSet

# ===========================================================================
# LONG CONFIGURATION
# ===========================================================================

# ---------------------------------------------------------------------------
# Coins with destructive LONG performance — suppress LONG entirely.
# threshold=1.0 is mathematically impossible to exceed (probas sum to 1).
# ---------------------------------------------------------------------------
# Evidence (backtest 2026-06-02):
#   STXUSDT:  16% LONG WR, negative return total
#   FILUSDT:  negative return total
#   ADAUSDT:  19% LONG WR
#   RUNEUSDT: 0% LONG WR
# Additional evidence (pass 2, 2026-06-03):
#   LINKUSDT: 26.2% LONG WR — no edge despite lower threshold
#   ALGOUSDT: 25.9% LONG WR
#   UNIUSDT:  32.5% LONG WR — below break-even
#   AAVEUSDT: 30.4% LONG WR — no improvement from 0.45 threshold
LONG_DISABLED_COINS: FrozenSet[str] = frozenset({
    "STXUSDT",   # 16% LONG WR, negative return
    "FILUSDT",   # negative return total
    "ADAUSDT",   # 19% LONG WR
    "RUNEUSDT",  # 0% LONG WR
    "LINKUSDT",  # 26.2% LONG WR — no edge despite lower threshold
    "ALGOUSDT",  # 25.9% LONG WR
    "UNIUSDT",   # 32.5% LONG WR — below break-even
    "AAVEUSDT",  # 30.4% LONG WR — no improvement from 0.45 threshold
})

# ---------------------------------------------------------------------------
# Coins with confirmed LONG edge (≥50% WR) — lower threshold to capture alpha.
# Evidence:
#   ARBUSDT: 58.4% LONG WR confirmed in pass 2 (stable) → threshold 0.40
# ---------------------------------------------------------------------------
LONG_OPTIMIZED_COINS: Dict[str, float] = {
    "ARBUSDT": 0.40,  # 58.4% LONG WR — only confirmed LONG-alpha coin
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


# ===========================================================================
# SHORT CONFIGURATION
# ===========================================================================

# ---------------------------------------------------------------------------
# Coins with destructive SHORT performance — suppress SHORT entirely.
# Evidence (backtest 2026-06-03, 25 tickers):
#   STXUSDT:  10.6% SHORT WR (179 signals) — far below 37.5% break-even
#   SUIUSDT:  33.3% SHORT WR (123 signals) — below break-even
#   UNIUSDT:  35.8% SHORT WR ( 81 signals) — below break-even
#   FILUSDT:  35.7% SHORT WR (185 signals) — below break-even
# ---------------------------------------------------------------------------
SHORT_DISABLED_COINS: FrozenSet[str] = frozenset({
    "STXUSDT",   # 10.6% SHORT WR — catastrophic, -28% return
    "SUIUSDT",   # 33.3% SHORT WR — below break-even
    "UNIUSDT",   # 35.8% SHORT WR — below break-even
    "FILUSDT",   # 35.7% SHORT WR — below break-even
})

# ---------------------------------------------------------------------------
# Coins with especially strong SHORT edge — lower threshold to capture alpha.
# Evidence (backtest 2026-06-03):
#   ATOMUSDT: 60.9% SHORT WR (419 signals) — strongest SHORT coin
#   OPUSDT:   60.0% SHORT WR (270 signals)
# ---------------------------------------------------------------------------
SHORT_OPTIMIZED_COINS: Dict[str, float] = {
    "ATOMUSDT": 0.30,  # 60.9% SHORT WR — high conviction, lower bar
    "OPUSDT":   0.30,  # 60.0% SHORT WR
}

# Default SHORT threshold: EV positive at 0.35 for most coins (47.5% avg WR).
# We keep it at 0.35 — it's already validated.
DEFAULT_SHORT_THRESHOLD: float = 0.35


def get_short_threshold(ticker: str) -> float:
    """
    Return the SHORT probability threshold for a given ticker.

    - Disabled coins:  1.0 (mathematically impossible → always HOLD)
    - Optimized coins: coin-specific lower threshold
    - All others:      DEFAULT_SHORT_THRESHOLD (0.35)

    Args:
        ticker: Coin symbol with USDT suffix, e.g. 'STXUSDT'.

    Returns:
        float threshold in (0.0, 1.0].
    """
    if ticker in SHORT_DISABLED_COINS:
        return 1.0
    if ticker in SHORT_OPTIMIZED_COINS:
        return SHORT_OPTIMIZED_COINS[ticker]
    return DEFAULT_SHORT_THRESHOLD
