"""Tests for TradingBot.start() retry logic on Binance connectivity failure."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.bot.trading_bot import TradingBot


def _make_mock_bot():
    """Minimal MagicMock acting as TradingBot self — no constructor needed."""
    bot = MagicMock()
    bot._market_scan_loop = AsyncMock()
    bot._position_monitoring_loop = AsyncMock()
    bot._binance_sync_loop = AsyncMock()
    bot._auto_training_loop = AsyncMock()
    bot.is_running = False
    bot.cycle_number = 0
    return bot


@pytest.mark.asyncio
async def test_retries_3_times_then_continues():
    """After 3 failures bot must NOT abort — update_bot_status must still be called."""
    bot = _make_mock_bot()
    bot.binance.test_connectivity.side_effect = [False, False, False]

    with patch("asyncio.sleep", new=AsyncMock()):
        await TradingBot.start(bot)

    assert bot.binance.test_connectivity.call_count == 3
    bot.db.update_bot_status.assert_called()


@pytest.mark.asyncio
async def test_succeeds_on_second_attempt():
    """Second attempt succeeds — connectivity called exactly twice, bot starts."""
    bot = _make_mock_bot()
    bot.binance.test_connectivity.side_effect = [False, True]

    with patch("asyncio.sleep", new=AsyncMock()):
        await TradingBot.start(bot)

    assert bot.binance.test_connectivity.call_count == 2
    bot.db.update_bot_status.assert_called()


@pytest.mark.asyncio
async def test_no_sleep_on_immediate_success():
    """No retry delay when first attempt succeeds."""
    bot = _make_mock_bot()
    bot.binance.test_connectivity.return_value = True

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await TradingBot.start(bot)

    assert bot.binance.test_connectivity.call_count == 1
    mock_sleep.assert_not_called()
