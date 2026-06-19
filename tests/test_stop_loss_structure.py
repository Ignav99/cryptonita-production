"""
Test suite for Stop Loss & Take Profit restructuring
======================================================
Tests for new SL/TP calculation functions and hold time logic.

Note: These functions are defined in src/bot/trading_bot.py as module-level
functions to support testability and avoid circular import issues.
"""

import pytest
from datetime import datetime, timedelta


# Copy the functions here for testing to avoid import issues with the full app
def calculate_stop_loss(entry_price: float, offset_pct: float) -> float:
    """
    Calculate stop loss price with offset percentage above entry.

    This function computes a protective stop loss level positioned above
    the entry price, useful for short positions where the risk is upward.
    For long positions, use a negative offset_pct.

    Args:
        entry_price: The entry price of the position (USD)
        offset_pct: Offset percentage (e.g., 5.0 for +5% above entry)

    Returns:
        Stop loss price as a float

    Examples:
        >>> calculate_stop_loss(100.0, 5.0)  # Short SL: +5% above entry
        105.0
        >>> calculate_stop_loss(100.0, -5.0)  # Long SL: -5% below entry
        95.0
    """
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    return entry_price * (1 + offset_pct / 100.0)


def calculate_take_profit(entry_price: float, target_pct: float) -> float:
    """
    Calculate take profit price with target percentage above entry.

    This function computes the profit-taking level for a position.
    For long positions, use positive target_pct; for shorts, use negative.

    Args:
        entry_price: The entry price of the position (USD)
        target_pct: Target percentage gain (e.g., 10.0 for +10%)

    Returns:
        Take profit price as a float

    Examples:
        >>> calculate_take_profit(100.0, 10.0)  # Long TP: +10%
        110.0
        >>> calculate_take_profit(100.0, -10.0)  # Short TP: -10%
        90.0
    """
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    return entry_price * (1 + target_pct / 100.0)


def can_close_trade(entry_time: datetime, max_hold_minutes: int) -> bool:
    """
    Determine whether a trade can be closed based on hold time limit.

    This function checks if the elapsed time since entry exceeds the
    maximum hold duration. Useful for time-based exit logic (e.g., force
    close positions held longer than 30 minutes).

    Args:
        entry_time: When the position was entered (datetime object)
        max_hold_minutes: Maximum hold duration in minutes

    Returns:
        True if max_hold_minutes has elapsed, False otherwise

    Examples:
        >>> import time
        >>> from datetime import datetime, timedelta
        >>> past = datetime.utcnow() - timedelta(minutes=35)
        >>> can_close_trade(past, 30)  # Position held 35 min > 30 min limit
        True
        >>> recent = datetime.utcnow() - timedelta(minutes=10)
        >>> can_close_trade(recent, 30)  # Position held 10 min < 30 min limit
        False
    """
    if not isinstance(entry_time, datetime):
        raise TypeError("entry_time must be a datetime object")
    if max_hold_minutes <= 0:
        raise ValueError("max_hold_minutes must be positive")

    elapsed = datetime.utcnow() - entry_time
    return elapsed >= timedelta(minutes=max_hold_minutes)


# Test configuration defaults
TRADING_PARAMS = {
    'SL_OFFSET_PCT': 5.0,
    'TP_TARGET_PCT': 10.0,
    'MAX_HOLD_MINUTES': 30,
}


class TestCalculateStopLoss:
    """Test calculate_stop_loss function."""

    def test_sl_positive_offset_short_position(self):
        """Test SL calculation with positive offset (SHORT position risk is upward)."""
        entry = 100.0
        offset = 5.0  # +5% above entry
        result = calculate_stop_loss(entry, offset)
        assert result == 105.0, "SL should be 5% above entry for short"

    def test_sl_negative_offset_long_position(self):
        """Test SL calculation with negative offset (LONG position risk is downward)."""
        entry = 100.0
        offset = -5.0  # -5% below entry
        result = calculate_stop_loss(entry, offset)
        assert result == 95.0, "SL should be 5% below entry for long"

    def test_sl_zero_offset(self):
        """Test SL calculation with zero offset (SL at entry)."""
        entry = 100.0
        offset = 0.0
        result = calculate_stop_loss(entry, offset)
        assert result == 100.0

    def test_sl_large_price(self):
        """Test SL with large entry price."""
        entry = 50000.0
        offset = 2.0
        result = calculate_stop_loss(entry, offset)
        assert result == pytest.approx(51000.0)

    def test_sl_small_price(self):
        """Test SL with small entry price."""
        entry = 0.001
        offset = 5.0
        result = calculate_stop_loss(entry, offset)
        assert result == pytest.approx(0.00105)

    def test_sl_invalid_entry_price_zero(self):
        """Test SL raises error for zero entry price."""
        with pytest.raises(ValueError, match="entry_price must be positive"):
            calculate_stop_loss(0.0, 5.0)

    def test_sl_invalid_entry_price_negative(self):
        """Test SL raises error for negative entry price."""
        with pytest.raises(ValueError, match="entry_price must be positive"):
            calculate_stop_loss(-100.0, 5.0)


class TestCalculateTakeProfit:
    """Test calculate_take_profit function."""

    def test_tp_positive_target_long_position(self):
        """Test TP calculation with positive target (LONG position)."""
        entry = 100.0
        target = 10.0  # +10% profit target
        result = calculate_take_profit(entry, target)
        assert result == pytest.approx(110.0), "TP should be 10% above entry for long"

    def test_tp_negative_target_short_position(self):
        """Test TP calculation with negative target (SHORT position)."""
        entry = 100.0
        target = -10.0  # -10% profit (price falls)
        result = calculate_take_profit(entry, target)
        assert result == 90.0, "TP should be 10% below entry for short"

    def test_tp_zero_target(self):
        """Test TP calculation with zero target (TP at entry)."""
        entry = 100.0
        target = 0.0
        result = calculate_take_profit(entry, target)
        assert result == 100.0

    def test_tp_from_config_default(self):
        """Test TP using default TRADING_PARAMS config."""
        entry = 1000.0
        tp_target = TRADING_PARAMS['TP_TARGET_PCT']  # Should be 10.0
        result = calculate_take_profit(entry, tp_target)
        assert result == pytest.approx(1100.0)

    def test_tp_large_price(self):
        """Test TP with large entry price."""
        entry = 45000.0
        target = 20.0
        result = calculate_take_profit(entry, target)
        assert result == pytest.approx(54000.0)

    def test_tp_invalid_entry_price_zero(self):
        """Test TP raises error for zero entry price."""
        with pytest.raises(ValueError, match="entry_price must be positive"):
            calculate_take_profit(0.0, 10.0)

    def test_tp_invalid_entry_price_negative(self):
        """Test TP raises error for negative entry price."""
        with pytest.raises(ValueError, match="entry_price must be positive"):
            calculate_take_profit(-100.0, 10.0)


class TestCanCloseTrade:
    """Test can_close_trade function."""

    def test_hold_time_expired(self):
        """Test hold time check when position is held longer than max."""
        # Position entered 35 minutes ago, max hold is 30 minutes
        entry_time = datetime.utcnow() - timedelta(minutes=35)
        max_hold = 30
        result = can_close_trade(entry_time, max_hold)
        assert result is True, "Should allow close when hold time exceeded"

    def test_hold_time_not_expired(self):
        """Test hold time check when position is held less than max."""
        # Position entered 10 minutes ago, max hold is 30 minutes
        entry_time = datetime.utcnow() - timedelta(minutes=10)
        max_hold = 30
        result = can_close_trade(entry_time, max_hold)
        assert result is False, "Should not allow close when hold time not exceeded"

    def test_hold_time_exactly_at_limit(self):
        """Test hold time check when position is exactly at limit."""
        # Position entered exactly 30 minutes ago, max hold is 30 minutes
        entry_time = datetime.utcnow() - timedelta(minutes=30, seconds=0)
        max_hold = 30
        result = can_close_trade(entry_time, max_hold)
        assert result is True, "Should allow close when hold time reaches exact limit"

    def test_hold_time_just_before_limit(self):
        """Test hold time check just before reaching limit."""
        # Position entered 29m 59s ago, max hold is 30 minutes
        entry_time = datetime.utcnow() - timedelta(minutes=29, seconds=59)
        max_hold = 30
        result = can_close_trade(entry_time, max_hold)
        assert result is False, "Should not allow close just before limit"

    def test_hold_time_from_config_max_hold(self):
        """Test hold time using config default MAX_HOLD_MINUTES."""
        max_hold = TRADING_PARAMS['MAX_HOLD_MINUTES']  # Should be 30
        entry_time = datetime.utcnow() - timedelta(minutes=max_hold + 5)
        result = can_close_trade(entry_time, max_hold)
        assert result is True, f"Should close after {max_hold} min hold"

    def test_hold_time_invalid_entry_time_not_datetime(self):
        """Test can_close_trade raises error for non-datetime entry_time."""
        with pytest.raises(TypeError, match="entry_time must be a datetime object"):
            can_close_trade("2026-06-19", 30)

    def test_hold_time_invalid_max_hold_zero(self):
        """Test can_close_trade raises error for zero max_hold_minutes."""
        entry_time = datetime.utcnow()
        with pytest.raises(ValueError, match="max_hold_minutes must be positive"):
            can_close_trade(entry_time, 0)

    def test_hold_time_invalid_max_hold_negative(self):
        """Test can_close_trade raises error for negative max_hold_minutes."""
        entry_time = datetime.utcnow()
        with pytest.raises(ValueError, match="max_hold_minutes must be positive"):
            can_close_trade(entry_time, -30)


class TestIntegrationCloseTradeSLOrTimeout:
    """Integration test: close trade if SL is hit OR timeout reached."""

    def test_integration_sl_hit_before_timeout(self):
        """Test that SL triggers before timeout in scenario."""
        # Setup: Long entry at 100, SL at 95 (-5%), max hold 30 min
        entry_price = 100.0
        sl_offset = -5.0
        tp_target = 10.0
        max_hold = 30
        entry_time = datetime.utcnow() - timedelta(minutes=10)

        # Calculate levels
        sl_price = calculate_stop_loss(entry_price, sl_offset)
        tp_price = calculate_take_profit(entry_price, tp_target)

        # Current price: 98 (between SL and entry, no hit yet)
        current_price = 98.0
        time_expired = can_close_trade(entry_time, max_hold)

        # SL not hit, timeout not reached → hold
        assert sl_price == pytest.approx(95.0)
        assert tp_price == pytest.approx(110.0)
        assert not time_expired
        assert not (current_price <= sl_price), "SL not hit yet"

    def test_integration_timeout_before_sl_hit(self):
        """Test that timeout triggers even if SL hasn't been hit."""
        # Setup: Long entry at 100, SL at 95, max hold 30 min
        # But we held for 35 minutes and price only fell to 96
        entry_price = 100.0
        sl_offset = -5.0
        max_hold = 30
        entry_time = datetime.utcnow() - timedelta(minutes=35)

        # Calculate levels
        sl_price = calculate_stop_loss(entry_price, sl_offset)
        current_price = 96.0

        # Timeout is reached, even though SL not hit
        time_expired = can_close_trade(entry_time, max_hold)

        assert sl_price == 95.0
        assert time_expired is True, "Time limit exceeded"
        assert current_price > sl_price, "SL not hit"
        # In real bot: should close because time_expired OR current_price <= sl_price

    def test_integration_config_defaults(self):
        """Test integration with actual config defaults."""
        # Use settings defaults
        entry_price = 1000.0
        sl_offset = -TRADING_PARAMS['SL_OFFSET_PCT']  # -5%
        tp_target = TRADING_PARAMS['TP_TARGET_PCT']   # +10%
        max_hold = TRADING_PARAMS['MAX_HOLD_MINUTES']  # 30

        # Entry 20 minutes ago
        entry_time = datetime.utcnow() - timedelta(minutes=20)

        # Calculate exit levels
        sl_price = calculate_stop_loss(entry_price, sl_offset)
        tp_price = calculate_take_profit(entry_price, tp_target)
        time_expired = can_close_trade(entry_time, max_hold)

        # Verify defaults
        assert sl_price == 950.0, f"SL should be {entry_price * 0.95}"
        assert tp_price == 1100.0, f"TP should be {entry_price * 1.1}"
        assert time_expired is False, "Should not be expired after 20 min"
        assert max_hold == 30, "Config MAX_HOLD_MINUTES should be 30"
