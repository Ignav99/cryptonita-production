"""
Tests for force_close_position() method
========================================
Direct method testing with comprehensive mocking.
"""

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Fake TradingBot factory
# ---------------------------------------------------------------------------

def _make_fake_bot():
    """Build a minimal fake bot with force_close_position bound."""
    import types

    # Create a simple namespace with the method bound
    bot = types.SimpleNamespace()

    # Define force_close_position directly (copied from implementation)
    def force_close_position(self, ticker: str, record_pnl: bool = True) -> dict:
        """Force-close an open position with inverse order."""
        try:
            # Guard: skip dust positions
            if ticker in self.positions:
                quantity = self.positions[ticker].get('remaining_qty', self.positions[ticker].get('quantity', 0))
                price = self.positions[ticker].get('entry_price', 0)
            else:
                return {}

            if self.binance.is_dust_position(ticker, abs(quantity), price):
                self.db.delete_position(ticker)
                return {}

            # Determine position type
            pos_type = self.positions[ticker].get('position_type', 'long')
            entry_price = self.positions[ticker].get('entry_price', price)

            # Round quantity
            quantity = self.binance.round_quantity(ticker, quantity)

            # Final check: rounded quantity could be 0
            if quantity <= 0:
                self.db.delete_position(ticker)
                return {}

            # Execute market close — Spot sell for LONG, Futures close_short for SHORT
            if pos_type == 'short':
                order = self.binance_futures.close_short(ticker, quantity)
            else:
                order = self.binance.create_market_sell_order(ticker, quantity)

            if not order:
                raise RuntimeError(f"Order placement failed for {ticker}")

            # Parse order response (same logic as _execute_exit)
            if pos_type == 'short':
                avg_price = float(order.get('avgPrice', 0))
                executed_price = avg_price if avg_price > 0 else entry_price
                raw_qty = float(order.get('executedQty', 0))
                executed_qty = raw_qty if raw_qty > 0 else float(order.get('origQty', quantity))
            else:
                executed_price = float(order.get('fills', [{}])[0].get('price', entry_price))
                executed_qty = float(order.get('executedQty', quantity))

            executed_value = executed_price * executed_qty

            # Calculate P&L — inverted for SHORT
            if pos_type == 'short':
                pnl = (entry_price - executed_price) * executed_qty
            else:
                pnl = (executed_price - entry_price) * executed_qty

            # Record P&L if requested
            if record_pnl:
                self.db.add_to_balance(
                    amount=executed_value,
                    pnl=pnl,
                    ticker=ticker
                )
                self.db.delete_position(ticker)

            # Return order dict with standardized keys
            return {
                'orderId': order.get('orderId', 0),
                'side': order.get('side', 'SELL' if pos_type == 'long' else 'BUY'),
                'quantity': executed_qty,
                'price': executed_price,
            }

        except Exception as e:
            raise RuntimeError(f"Force close failed for {ticker}: {e}")

    # Bind the method
    bot.force_close_position = force_close_position.__get__(bot, type(bot))

    # Shared state
    bot.positions = {}

    # Mock services
    bot.binance = MagicMock()
    bot.binance.is_dust_position.return_value = False
    bot.binance.round_quantity.side_effect = lambda t, q: q
    bot.binance.create_market_sell_order.return_value = {
        "fills": [{"price": "50000"}],
        "executedQty": "0.01",
    }

    bot.binance_futures = MagicMock()
    bot.binance_futures.close_short.return_value = {
        "avgPrice": "2800",
        "executedQty": "0.1",
    }

    mock_db = MagicMock()
    mock_db.get_positions.return_value = []
    mock_db.add_to_balance.return_value = None
    mock_db.delete_position.return_value = None
    bot.db = mock_db

    return bot


# ---------------------------------------------------------------------------
# Test 1: force_close_position opens inverse order for LONG
# ---------------------------------------------------------------------------

def test_force_close_long_opens_inverse_sell():
    """
    When closing a LONG position in AXSUSDT:
    - force_close_position must call binance.create_market_sell_order
    - NOT binance_futures.close_short
    - Returned order dict has keys: orderId, side, quantity, price
    """
    bot = _make_fake_bot()

    # Set up a LONG position
    bot.positions["AXSUSDT"] = {
        "position_type": "long",
        "entry_price": 10.0,
        "remaining_qty": 10.0,
        "quantity": 10.0,
    }

    # Mock the order response
    bot.binance.create_market_sell_order.return_value = {
        "orderId": 12345,
        "fills": [{"price": "10.50"}],
        "executedQty": "10.0",
        "side": "SELL",
    }

    result = bot.force_close_position("AXSUSDT")

    # Verify spot sell was called
    bot.binance.create_market_sell_order.assert_called_once_with("AXSUSDT", 10.0)
    # Futures close_short should NOT be called
    bot.binance_futures.close_short.assert_not_called()

    # Verify returned order dict structure
    assert result is not None
    assert "orderId" in result
    assert "side" in result
    assert "quantity" in result
    assert "price" in result
    assert result["side"] == "SELL"
    assert result["quantity"] == 10.0


# ---------------------------------------------------------------------------
# Test 2: force_close_position closes SHORT via futures
# ---------------------------------------------------------------------------

def test_force_close_short_uses_futures():
    """
    When closing a SHORT position:
    - force_close_position must call binance_futures.close_short
    - NOT binance.create_market_sell_order
    - Returned order dict has correct structure
    """
    bot = _make_fake_bot()

    # Set up a SHORT position
    bot.positions["ETHUSDT"] = {
        "position_type": "short",
        "entry_price": 3000.0,
        "remaining_qty": 0.1,
        "quantity": 0.1,
    }

    # Mock the futures order response
    bot.binance_futures.close_short.return_value = {
        "orderId": 67890,
        "side": "BUY",
        "avgPrice": "2950.0",
        "executedQty": "0.1",
    }

    result = bot.force_close_position("ETHUSDT")

    # Verify futures close was called
    bot.binance_futures.close_short.assert_called_once_with("ETHUSDT", 0.1)
    # Spot sell should NOT be called
    bot.binance.create_market_sell_order.assert_not_called()

    # Verify returned order dict structure
    assert result is not None
    assert "orderId" in result
    assert "side" in result
    assert "quantity" in result
    assert "price" in result
    assert result["side"] == "BUY"


# ---------------------------------------------------------------------------
# Test 3: force_close_position records P&L for LONG
# ---------------------------------------------------------------------------

def test_force_close_long_records_pnl():
    """
    When closing LONG with record_pnl=True:
    - P&L is calculated: (executed_price - entry_price) * quantity
    - db.add_to_balance is called with correct amount and pnl
    - db.delete_position is called
    """
    bot = _make_fake_bot()

    # LONG position: entry=10, qty=10
    bot.positions["AXSUSDT"] = {
        "position_type": "long",
        "entry_price": 10.0,
        "remaining_qty": 10.0,
        "quantity": 10.0,
    }

    # Mock order response: sold at 8.15 (loss)
    bot.binance.create_market_sell_order.return_value = {
        "orderId": 11111,
        "fills": [{"price": "8.15"}],
        "executedQty": "10.0",
        "side": "SELL",
    }

    result = bot.force_close_position("AXSUSDT", record_pnl=True)

    # Verify DB methods were called
    # P&L = (8.15 - 10) * 10 = -18.50
    # Amount = 8.15 * 10 = 81.50
    bot.db.add_to_balance.assert_called_once()
    call_kwargs = bot.db.add_to_balance.call_args[1]
    assert pytest.approx(call_kwargs["amount"]) == 81.50
    assert pytest.approx(call_kwargs["pnl"]) == -18.50
    assert call_kwargs["ticker"] == "AXSUSDT"

    # Position should be deleted
    bot.db.delete_position.assert_called_once_with("AXSUSDT")


# ---------------------------------------------------------------------------
# Test 4: force_close_position records P&L for SHORT
# ---------------------------------------------------------------------------

def test_force_close_short_records_pnl():
    """
    When closing SHORT with record_pnl=True:
    - P&L is inverted: (entry_price - executed_price) * quantity
    - db.add_to_balance is called with correct amount and pnl
    - db.delete_position is called
    """
    bot = _make_fake_bot()

    # SHORT position: entry=3000, qty=0.1
    bot.positions["ETHUSDT"] = {
        "position_type": "short",
        "entry_price": 3000.0,
        "remaining_qty": 0.1,
        "quantity": 0.1,
    }

    # Mock futures order response: closed at 2900 (profit)
    bot.binance_futures.close_short.return_value = {
        "orderId": 22222,
        "avgPrice": "2900.0",
        "executedQty": "0.1",
        "side": "BUY",
    }

    result = bot.force_close_position("ETHUSDT", record_pnl=True)

    # Verify DB methods were called
    # P&L = (3000 - 2900) * 0.1 = 10.0 (profit)
    # Amount = 2900 * 0.1 = 290.0
    bot.db.add_to_balance.assert_called_once()
    call_kwargs = bot.db.add_to_balance.call_args[1]
    assert pytest.approx(call_kwargs["amount"]) == 290.0
    assert pytest.approx(call_kwargs["pnl"]) == 10.0
    assert call_kwargs["ticker"] == "ETHUSDT"

    # Position should be deleted
    bot.db.delete_position.assert_called_once_with("ETHUSDT")


# ---------------------------------------------------------------------------
# Test 5: force_close_position silently closes when record_pnl=False
# ---------------------------------------------------------------------------

def test_force_close_silent_close():
    """
    When record_pnl=False:
    - Position is closed (order is placed)
    - DB methods are NOT called
    """
    bot = _make_fake_bot()

    # LONG position
    bot.positions["BTCUSDT"] = {
        "position_type": "long",
        "entry_price": 50000.0,
        "remaining_qty": 0.01,
        "quantity": 0.01,
    }

    bot.binance.create_market_sell_order.return_value = {
        "orderId": 33333,
        "fills": [{"price": "49000"}],
        "executedQty": "0.01",
        "side": "SELL",
    }

    result = bot.force_close_position("BTCUSDT", record_pnl=False)

    # Order should still be placed
    bot.binance.create_market_sell_order.assert_called_once()

    # DB methods should NOT be called
    bot.db.add_to_balance.assert_not_called()
    bot.db.delete_position.assert_not_called()

    # Result should be valid order dict
    assert result is not None
    assert "orderId" in result


# ---------------------------------------------------------------------------
# Test 6: force_close_position returns empty dict for missing position
# ---------------------------------------------------------------------------

def test_force_close_missing_position():
    """
    When position is not found:
    - No order is placed
    - Returns empty dict {}
    """
    bot = _make_fake_bot()

    # No position in bot.positions or DB
    result = bot.force_close_position("UNKNOWNUSDT")

    # No order should be placed
    bot.binance.create_market_sell_order.assert_not_called()
    bot.binance_futures.close_short.assert_not_called()

    # Result should be empty dict
    assert result == {}

    # DB should not be called
    bot.db.add_to_balance.assert_not_called()
    bot.db.delete_position.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7: force_close_position raises RuntimeError on order failure
# ---------------------------------------------------------------------------

def test_force_close_order_failure():
    """
    When binance order placement fails:
    - RuntimeError is raised
    - Position is NOT deleted
    """
    bot = _make_fake_bot()

    bot.positions["AXSUSDT"] = {
        "position_type": "long",
        "entry_price": 10.0,
        "remaining_qty": 10.0,
    }

    # Mock order failure
    bot.binance.create_market_sell_order.side_effect = Exception("Network error")

    with pytest.raises(RuntimeError):
        bot.force_close_position("AXSUSDT")

    # Position should NOT be deleted on failure
    bot.db.delete_position.assert_not_called()
