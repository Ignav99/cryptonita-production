"""
KELLY CRITERION POSITION SIZER
================================
Fractional Kelly (25%) with regime-based scaling.
- Formula: f = 0.25 * (p * b - q) / b
- Clamped to [2%, 15%] of portfolio
- Scaled by regime: Bull=1.0x, Sideways=0.7x, Bear=0.5x
"""

import numpy as np
from typing import Dict, Optional
from loguru import logger


class KellyPositionSizer:
    """
    Position sizing using fractional Kelly Criterion.
    """

    def __init__(
        self,
        kelly_fraction: float = 0.25,
        min_position_pct: float = 0.02,
        max_position_pct: float = 0.15,
        default_win_loss_ratio: float = 2.0,
    ):
        """
        Args:
            kelly_fraction: Fraction of full Kelly to use (0.25 = quarter Kelly)
            min_position_pct: Minimum position size as % of portfolio
            max_position_pct: Maximum position size as % of portfolio
            default_win_loss_ratio: Default avg_win/avg_loss ratio
        """
        self.kelly_fraction = kelly_fraction
        self.min_pct = min_position_pct
        self.max_pct = max_position_pct
        self.default_b = default_win_loss_ratio

    def calculate_kelly(
        self,
        win_prob: float,
        win_loss_ratio: Optional[float] = None,
    ) -> float:
        """
        Calculate fractional Kelly bet size.

        Args:
            win_prob: Probability of winning (from model)
            win_loss_ratio: avg_win / avg_loss (b in Kelly formula)

        Returns:
            Optimal fraction of bankroll to bet
        """
        b = win_loss_ratio or self.default_b
        p = win_prob
        q = 1 - p

        # Kelly formula: f* = (p*b - q) / b
        full_kelly = (p * b - q) / b

        # Fractional Kelly for safety
        f = self.kelly_fraction * full_kelly

        return f

    def calculate_position_size(
        self,
        current_price: float,
        portfolio_value: float,
        probability: float,
        regime_data: Optional[Dict] = None,
        win_loss_ratio: Optional[float] = None,
        max_position_usd: float = 500.0,
        kelly_mult: float = 1.0,
        max_position_pct_override: Optional[float] = None,
        correlation_mult: float = 1.0,
    ) -> Dict[str, float]:
        """
        Calculate position size with Kelly + regime scaling + tier adjustments + correlation penalty.

        Args:
            current_price: Current asset price
            portfolio_value: Total portfolio value in USD
            probability: Model prediction probability
            regime_data: Dict with regime_name from RegimeDetector
            win_loss_ratio: Historical avg_win/avg_loss
            max_position_usd: Hard cap on position size
            kelly_mult: Tier-based Kelly multiplier (e.g., 1.2 for blue chips, 0.5 for memes)
            max_position_pct_override: Tier-based max position % override
            correlation_mult: Correlation penalty multiplier [0.5, 1.0] from CorrelationEngine

        Returns:
            Dict with quantity, usd_value, position_pct, kelly_raw
        """
        # Calculate raw Kelly fraction
        kelly_raw = self.calculate_kelly(probability, win_loss_ratio)

        # Apply tier Kelly multiplier
        kelly_adjusted = kelly_raw * kelly_mult

        # Use tier max position or default
        effective_max_pct = max_position_pct_override if max_position_pct_override is not None else self.max_pct

        # Clamp to [min, max]
        position_pct = max(self.min_pct, min(effective_max_pct, kelly_adjusted))

        # Apply regime scaling
        regime_mult = self._get_regime_multiplier(regime_data)
        position_pct *= regime_mult

        # Apply correlation penalty (reduces size for correlated positions)
        position_pct *= correlation_mult

        # Re-clamp after regime + correlation scaling
        position_pct = max(self.min_pct, min(effective_max_pct, position_pct))

        # Calculate USD value
        usd_value = portfolio_value * position_pct
        usd_value = min(usd_value, max_position_usd)

        # Calculate quantity
        quantity = usd_value / current_price if current_price > 0 else 0.0

        result = {
            "quantity": quantity,
            "usd_value": usd_value,
            "position_pct": position_pct * 100,
            "kelly_raw": kelly_raw,
            "kelly_mult": kelly_mult,
            "regime_multiplier": regime_mult,
            "correlation_multiplier": correlation_mult,
        }

        logger.debug(
            f"Kelly: raw={kelly_raw:.4f}, mult={kelly_mult}x, pct={position_pct*100:.1f}%, "
            f"regime={regime_mult:.1f}x, corr={correlation_mult:.2f}x, usd=${usd_value:.2f}"
        )

        return result

    def _get_regime_multiplier(self, regime_data: Optional[Dict]) -> float:
        """Get position size multiplier based on market regime"""
        if regime_data is None:
            return 0.7  # Default: conservative (sideways)

        name = regime_data.get("regime_name", "Sideways")
        multipliers = {
            "Bull": 1.0,
            "Sideways": 0.7,
            "Bear": 0.5,
        }
        return multipliers.get(name, 0.7)

    def update_win_loss_ratio(self, trades: list) -> float:
        """
        Calculate win/loss ratio from historical trades.

        Args:
            trades: List of dicts with 'pnl' key

        Returns:
            Updated win/loss ratio
        """
        if not trades:
            return self.default_b

        wins = [t["pnl"] for t in trades if t.get("pnl", 0) > 0]
        losses = [abs(t["pnl"]) for t in trades if t.get("pnl", 0) < 0]

        if not wins or not losses:
            return self.default_b

        avg_win = np.mean(wins)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return self.default_b

        ratio = avg_win / avg_loss
        logger.info(f"Updated win/loss ratio: {ratio:.2f} (wins={len(wins)}, losses={len(losses)})")
        return ratio
