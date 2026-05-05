"""
POSITION LIFECYCLE MANAGER
===========================
State machine for position lifecycle management.

States:
    INCUBATING -> GROWING -> PROFITING -> DECAYING -> ZOMBIE
         |           |           |           |
         +---------> EXIT <------+           +----> EXIT
         (SL hit)   (TP3/reversal)          (force close)

Only DECAYING and ZOMBIE positions are rotatable.
"""

from datetime import datetime
from typing import Dict
from loguru import logger

from config import settings
from src.models.hold_time_estimator import HoldTimeEstimator


# Lifecycle states
INCUBATING = "INCUBATING"
GROWING = "GROWING"
PROFITING = "PROFITING"
DECAYING = "DECAYING"
ZOMBIE = "ZOMBIE"

ROTATABLE_STATES = {DECAYING, ZOMBIE}


class PositionLifecycleManager:
    """Manages position lifecycle states and rotation eligibility."""

    def __init__(self, hold_estimator: HoldTimeEstimator):
        self.estimator = hold_estimator

    def on_entry(self, position: Dict, ticker: str, probability: float, tier: int) -> Dict:
        """
        Called when a new position is created.
        Attaches lifecycle metadata to the position dict.
        """
        estimate = self.estimator.estimate(ticker, probability, tier)

        position['lifecycle_state'] = INCUBATING
        position['predicted_hold_days'] = estimate['predicted_hold_days']
        position['max_hold_days'] = estimate['max_hold_days']
        position['expected_max_gain_pct'] = estimate['expected_max_gain_pct']
        position['hold_confidence'] = estimate['confidence']
        position['last_momentum_3d'] = 0.0
        position['exit_cooldowns'] = {}

        logger.info(
            f"Lifecycle: {ticker} entered INCUBATING "
            f"(predicted_hold={estimate['predicted_hold_days']:.0f}d, "
            f"max={estimate['max_hold_days']:.0f}d, "
            f"expected_gain={estimate['expected_max_gain_pct']*100:.1f}%)"
        )
        return position

    def get_state(self, position: Dict) -> str:
        """
        Calculate the current lifecycle state based on position data.
        """
        entry_price = position.get('entry_price', 0)
        current_price = position.get('current_price', entry_price)
        if entry_price <= 0:
            return INCUBATING

        pnl_pct = (current_price - entry_price) / entry_price
        predicted_hold = position.get('predicted_hold_days', 7.0)
        momentum = position.get('last_momentum_3d', 0.0)

        # Calculate days held
        entry_time = position.get('entry_time')
        if entry_time:
            if isinstance(entry_time, str):
                entry_time = datetime.fromisoformat(entry_time)
            days_held = (datetime.utcnow() - entry_time).total_seconds() / 86400
        else:
            days_held = 0

        # ZOMBIE: underwater > 7 days OR > predicted_hold * 2
        if (pnl_pct < 0 and days_held > 7) or days_held > predicted_hold * 2:
            return ZOMBIE

        # DECAYING: past predicted_hold AND momentum negative AND no TP1 hit
        tp1_hit = position.get('tp1_hit', False)
        if days_held > predicted_hold and momentum < 0 and not tp1_hit:
            return DECAYING

        # PROFITING: TP1 hit OR pnl > 8%
        if tp1_hit or pnl_pct > 0.08:
            return PROFITING

        # INCUBATING: early phase (< 25% of predicted hold)
        incubation_threshold = predicted_hold * settings.INCUBATION_PCT
        if days_held < incubation_threshold:
            return INCUBATING

        # GROWING: positive momentum, not underwater, within predicted hold
        if momentum >= 0 and pnl_pct >= -0.02 and days_held <= predicted_hold:
            return GROWING

        # Default to GROWING if within predicted hold
        if days_held <= predicted_hold:
            return GROWING

        return DECAYING

    def update_state(self, position: Dict, ticker: str) -> str:
        """Update the lifecycle state in the position dict. Returns new state."""
        old_state = position.get('lifecycle_state', INCUBATING)
        new_state = self.get_state(position)

        if new_state != old_state:
            position['lifecycle_state'] = new_state
            logger.info(f"Lifecycle: {ticker} {old_state} -> {new_state}")

        return new_state

    def is_rotatable(self, position: Dict) -> bool:
        """Only DECAYING and ZOMBIE positions can be rotated out."""
        state = self.get_state(position)
        return state in ROTATABLE_STATES

    def should_force_close(self, position: Dict) -> bool:
        """Check if a zombie position should be force closed."""
        if self.get_state(position) != ZOMBIE:
            return False

        entry_time = position.get('entry_time')
        if not entry_time:
            return False
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)

        days_held = (datetime.utcnow() - entry_time).total_seconds() / 86400
        return days_held >= settings.MAX_ZOMBIE_DAYS

    def on_close(self, position: Dict, ticker: str) -> None:
        """Called when a position is closed. Updates estimator with real data."""
        entry_time = position.get('entry_time')
        if not entry_time:
            return
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)

        days_held = (datetime.utcnow() - entry_time).total_seconds() / 86400
        entry_price = position.get('entry_price', 0)
        current_price = position.get('current_price', entry_price)
        max_gain = (current_price - entry_price) / entry_price if entry_price > 0 else 0

        self.estimator.update_from_closed_trade({
            'tier': position.get('tier', 3),
            'probability': position.get('entry_probability', 0.30),
            'days_held': days_held,
            'max_gain_pct': max(max_gain, 0),
        })
        logger.info(f"Lifecycle: {ticker} closed after {days_held:.1f}d (gain={max_gain*100:+.1f}%)")
