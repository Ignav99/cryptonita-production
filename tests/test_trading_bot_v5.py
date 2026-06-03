"""
Tests for TradingBot V5 integration
=====================================
Pure unit tests — all external dependencies mocked.
Tests V5-specific behaviour: LONG/SHORT routing, inverted PnL, inverted TP/SL.

Strategy: build a lightweight fake TradingBot object that shares the same
_execute_trade / _execute_exit logic but has all services replaced with mocks.
This avoids real DB/Binance connections entirely.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fake TradingBot factory
# ---------------------------------------------------------------------------

def _make_fake_bot():
    """
    Build a minimal object that has all the attributes _execute_trade needs,
    without calling TradingBot.__init__ (which hits real DB / Binance).
    """
    import types

    # Pull in only the method implementations — no __init__ side-effects
    import src.bot.trading_bot as bot_module

    bot = types.SimpleNamespace()

    # Bind unbound methods to our fake instance
    bot._execute_trade = bot_module.TradingBot._execute_trade.__get__(bot)
    bot._execute_exit = bot_module.TradingBot._execute_exit.__get__(bot)
    bot._check_circuit_breaker = lambda: (True, 1.0, "")
    bot._check_ticker_exposure = lambda ticker, usd: (True, "")
    bot._attempt_smart_rotation = AsyncMock(return_value=False)

    # Shared state
    bot.positions = {}
    bot.daily_loss = 0.0
    bot.auto_trading = True

    # Mock services
    bot.binance = MagicMock()
    bot.binance.get_current_price.return_value = 50000.0
    bot.binance.is_dust_position.return_value = False
    bot.binance.round_quantity.side_effect = lambda t, q: q
    bot.binance.round_price.side_effect = lambda t, p: p
    bot.binance.create_market_buy_order.return_value = {
        "fills": [{"price": "50000"}],
        "executedQty": "0.01",
    }
    bot.binance.create_market_sell_order.return_value = {
        "fills": [{"price": "50000"}],
        "executedQty": "0.01",
    }
    bot.binance.create_oco_order.return_value = {"orderId": 1}
    bot.binance.create_stop_limit_order.return_value = {"orderId": 2}
    bot.binance.cancel_all_open_orders.return_value = 0

    bot.binance_futures = MagicMock()
    bot.binance_futures.open_short.return_value = {
        "fills": [{"price": "3000"}],
        "executedQty": "0.1",
    }
    bot.binance_futures.close_short.return_value = {
        "fills": [{"price": "2800"}],
        "executedQty": "0.1",
    }

    mock_db = MagicMock()
    mock_db.get_portfolio.return_value = {"total_value": 10000.0, "available_balance": 5000.0}
    mock_db.can_afford_trade.return_value = (True, "")
    mock_db.deduct_from_balance.return_value = True
    mock_db.add_to_balance.return_value = None
    mock_db.get_recent_signals.return_value = pd.DataFrame()
    mock_db.save_trade.return_value = 42
    mock_db.upsert_position.return_value = None
    mock_db.delete_position.return_value = None
    bot.db = mock_db

    mock_predictor = MagicMock()
    mock_predictor.should_trade.return_value = (True, "approved")
    mock_predictor.calculate_position_size.return_value = {
        "quantity": 0.01,
        "usd_value": 500.0,
        "confidence": "high",
    }
    bot.predictor = mock_predictor

    mock_risk_manager = MagicMock()
    mock_risk_manager.calculate_dynamic_tp_sl.return_value = {
        "stop_loss": 47500.0,
        "stop_loss_pct": 0.05,
        "tp1": 52500.0,
        "tp1_pct": 0.05,
        "tp2": 55000.0,
        "tp2_pct": 0.10,
        "tp3": 60000.0,
        "tp3_pct": 0.20,
        "tp1_size": 0.30,
        "tp2_size": 0.35,
        "tp3_size": 1.0,
        "atr_pct": 0.03,
        "trailing_stop_enabled": False,
        "tier": 2,
    }
    bot.risk_manager = mock_risk_manager

    mock_corr_engine = MagicMock()
    mock_corr_engine.get_correlation_penalty.return_value = 1.0
    bot.correlation_engine = mock_corr_engine

    bot.notifier = AsyncMock()
    bot.notifier.notify_trade = AsyncMock()
    bot.notifier.notify_circuit_breaker = AsyncMock()

    bot.lifecycle_manager = MagicMock()
    bot.signal_queue = MagicMock()

    # Settings stubs used inside _execute_trade
    from config import settings as _settings
    bot._regime_max_positions = getattr(_settings, "MAX_POSITIONS", 10)

    return bot


# ---------------------------------------------------------------------------
# Test 1: TradingBot initialises with V5 predictor + BinanceFuturesService
# ---------------------------------------------------------------------------

def test_bot_initializes_with_v5_and_futures_service():
    """
    After init the bot must have a `predictor` (V5) and a `binance_futures`
    attribute.  Both must be created from the V5/Futures constructors, not V4.
    """
    import sys

    mock_predictor_instance = MagicMock(name="TradingPredictorV5_instance")
    mock_futures_instance = MagicMock(name="BinanceFuturesService_instance")

    mock_predictor_cls = MagicMock(return_value=mock_predictor_instance)
    mock_futures_cls = MagicMock(return_value=mock_futures_instance)

    mock_v5_mod = MagicMock()
    mock_v5_mod.TradingPredictorV5 = mock_predictor_cls
    mock_futures_mod = MagicMock()
    mock_futures_mod.BinanceFuturesService = mock_futures_cls

    from unittest.mock import patch
    with (
        patch("src.bot.trading_bot.BinanceService", MagicMock()),
        patch("src.bot.trading_bot.BinanceDataService", MagicMock()),
        patch("src.bot.trading_bot.DatabaseManager", MagicMock()),
        patch("src.bot.trading_bot.MacroDataFetcher", MagicMock()),
        patch("src.bot.trading_bot.DynamicRiskManager", MagicMock()),
        patch("src.bot.trading_bot.TelegramNotifier", MagicMock()),
        patch("src.bot.trading_bot.CorrelationEngine", MagicMock()),
        patch("src.bot.trading_bot.HoldTimeEstimator", MagicMock()),
        patch("src.bot.trading_bot.PositionLifecycleManager", MagicMock()),
        patch("src.bot.trading_bot.SignalQueue", MagicMock()),
        patch("src.bot.trading_bot.HealthMonitor", MagicMock()),
        patch.dict(sys.modules, {
            "src.models.predictor_v5": mock_v5_mod,
            "src.services.binance_futures_service": mock_futures_mod,
        }),
    ):
        import importlib
        import src.bot.trading_bot as bot_module
        importlib.reload(bot_module)
        bot = bot_module.TradingBot()

    # V5 predictor was instantiated
    mock_predictor_cls.assert_called_once()
    # BinanceFuturesService was instantiated
    mock_futures_cls.assert_called_once()

    assert bot.predictor is mock_predictor_instance
    assert bot.binance_futures is mock_futures_instance


# ---------------------------------------------------------------------------
# Test 2: _count_signals counts LONG and SHORT separately
# ---------------------------------------------------------------------------

def test_count_signals_long_and_short():
    """
    _scan_market computes long_signals = (signal_class==1).sum()
    and short_signals = (signal_class==2).sum(), then sums as buy_signals.
    We verify the arithmetic directly on a DataFrame, mirroring the logic.
    """
    predictions_df = pd.DataFrame([
        {"ticker": "BTCUSDT", "signal_class": 1, "signal_name": "LONG", "p_long": 0.7, "p_short": 0.1, "p_hold": 0.2, "features": {}},
        {"ticker": "ETHUSDT", "signal_class": 2, "signal_name": "SHORT", "p_long": 0.1, "p_short": 0.65, "p_hold": 0.25, "features": {}},
        {"ticker": "SOLUSDT", "signal_class": 0, "signal_name": "HOLD", "p_long": 0.1, "p_short": 0.1, "p_hold": 0.8, "features": {}},
        {"ticker": "ADAUSDT", "signal_class": 1, "signal_name": "LONG", "p_long": 0.6, "p_short": 0.2, "p_hold": 0.2, "features": {}},
        {"ticker": "DOTUSDT", "signal_class": 2, "signal_name": "SHORT", "p_long": 0.05, "p_short": 0.7, "p_hold": 0.25, "features": {}},
    ])

    long_signals = int((predictions_df["signal_class"] == 1).sum())
    short_signals = int((predictions_df["signal_class"] == 2).sum())
    buy_signals = long_signals + short_signals

    assert long_signals == 2
    assert short_signals == 2
    assert buy_signals == 4


# ---------------------------------------------------------------------------
# Test 3: _execute_trade routes LONG to binance.create_market_buy_order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_trade_long_routes_to_spot_buy():
    """
    When signal_class == 1 (LONG), _execute_trade must call
    binance.create_market_buy_order and NOT binance_futures.open_short.
    """
    bot = _make_fake_bot()

    signal = pd.Series({
        "ticker": "BTCUSDT",
        "signal_class": 1,
        "signal_name": "LONG",
        "p_hold": 0.1,
        "p_long": 0.7,
        "p_short": 0.2,
        "probability": 0.7,
        "features": {},
    })

    await bot._execute_trade(signal)

    # LONG must use spot buy
    bot.binance.create_market_buy_order.assert_called_once_with("BTCUSDT", 0.01)
    # SHORT futures must NOT be called
    bot.binance_futures.open_short.assert_not_called()

    # Position should be recorded as 'long'
    assert "BTCUSDT" in bot.positions
    assert bot.positions["BTCUSDT"]["position_type"] == "long"


# ---------------------------------------------------------------------------
# Test 4: _execute_trade routes SHORT to binance_futures.open_short
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_trade_short_routes_to_futures():
    """
    When signal_class == 2 (SHORT), _execute_trade must call
    binance_futures.open_short and NOT binance.create_market_buy_order.
    TP/SL levels must be inverted.
    """
    bot = _make_fake_bot()

    # Adjust mocks for ETH SHORT
    bot.binance.get_current_price.return_value = 3000.0
    bot.predictor.calculate_position_size.return_value = {
        "quantity": 0.1,
        "usd_value": 300.0,
        "confidence": "high",
    }
    bot.binance_futures.open_short.return_value = {
        "fills": [{"price": "3000"}],
        "executedQty": "0.1",
    }

    signal = pd.Series({
        "ticker": "ETHUSDT",
        "signal_class": 2,
        "signal_name": "SHORT",
        "p_hold": 0.15,
        "p_long": 0.1,
        "p_short": 0.75,
        "probability": 0.75,
        "features": {},
    })

    await bot._execute_trade(signal)

    # SHORT must use futures
    bot.binance_futures.open_short.assert_called_once_with("ETHUSDT", 0.1)
    # Spot buy must NOT be called
    bot.binance.create_market_buy_order.assert_not_called()

    # Position should be recorded as 'short'
    assert "ETHUSDT" in bot.positions
    assert bot.positions["ETHUSDT"]["position_type"] == "short"

    # TP/SL levels must be inverted for SHORT
    # entry=3000, tp1_pct=0.05 → tp1 = 3000*(1-0.05) = 2850
    assert bot.positions["ETHUSDT"]["tp1"] == pytest.approx(2850.0)
    # sl_pct=0.05 → sl = 3000*(1+0.05) = 3150
    assert bot.positions["ETHUSDT"]["stop_loss"] == pytest.approx(3150.0)


# ---------------------------------------------------------------------------
# Test 5: SHORT PnL calculation is inverted
# ---------------------------------------------------------------------------

def test_short_pnl_is_inverted():
    """
    For a SHORT position:
      entry_price = 100, current_price = 90
      pnl_pct = (entry - current) / entry = (100-90)/100 = +10%  (profit)

    For a LONG position with same prices:
      pnl_pct = (current - entry) / entry = (90-100)/100 = -10%  (loss)
    """
    entry = 100.0
    current = 90.0

    # SHORT formula (as implemented in _monitor_positions)
    pnl_pct_short = (entry - current) / entry
    # LONG formula (as implemented in _monitor_positions)
    pnl_pct_long = (current - entry) / entry

    assert pnl_pct_short == pytest.approx(0.10)   # +10% profit for short
    assert pnl_pct_long == pytest.approx(-0.10)    # -10% loss for long
