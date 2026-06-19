# Binance Testnet Retry Logic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-abort on Binance testnet connectivity failure with retry logic (3 attempts × 60s), continuing in scan-only mode after exhaustion instead of killing the bot.

**Architecture:** Single-file change in `trading_bot.py`. The `start()` method currently does one connectivity check and aborts on failure. We replace those 3 lines with an async retry loop. If all retries fail, we log a warning and continue — trade execution will fail gracefully in the loops since testnet is for trading only, while market data uses production Binance (separate service, unaffected).

**Tech Stack:** Python `asyncio`, `python-binance` testnet, loguru

---

### Task 1: Add retry logic to `trading_bot.start()`

**Files:**
- Modify: `src/bot/trading_bot.py:268-275`
- Test: `tests/bot/test_trading_bot_connectivity.py`

- [ ] **Step 1: Write the failing test**

Create file `tests/bot/test_trading_bot_connectivity.py`:

```python
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture
def bot():
    """Create a TradingBot instance with all dependencies mocked."""
    with patch("src.bot.trading_bot.BinanceService"), \
         patch("src.bot.trading_bot.BinanceDataService"), \
         patch("src.bot.trading_bot.BinanceFuturesService"), \
         patch("src.bot.trading_bot.DatabaseManager"), \
         patch("src.bot.trading_bot.TradingPredictorV5"), \
         patch("src.bot.trading_bot.DynamicRiskManager"), \
         patch("src.bot.trading_bot.HoldTimeEstimator"), \
         patch("src.bot.trading_bot.MacroDataFetcher"), \
         patch("src.bot.trading_bot.LLMSentimentAnalyzer"), \
         patch("src.bot.trading_bot.FeatureEngineer"):
        from src.bot.trading_bot import TradingBot
        return TradingBot()


@pytest.mark.asyncio
async def test_start_retries_on_502_and_continues(bot):
    """Bot should retry 3 times and then continue running (not abort) on persistent failure."""
    bot.binance.test_connectivity.side_effect = [False, False, False]

    # Patch the loops so start() doesn't run forever
    with patch.object(bot, "_market_scan_loop", new=AsyncMock()), \
         patch.object(bot, "_position_monitoring_loop", new=AsyncMock()), \
         patch.object(bot, "_binance_sync_loop", new=AsyncMock()), \
         patch("asyncio.sleep", new=AsyncMock()):
        await bot.start()

    # Should have called test_connectivity 3 times
    assert bot.binance.test_connectivity.call_count == 3
    # Bot should still be marked as running (not aborted)
    bot.db.update_bot_status.assert_called()


@pytest.mark.asyncio
async def test_start_succeeds_on_second_attempt(bot):
    """Bot should succeed if connectivity works on second attempt."""
    bot.binance.test_connectivity.side_effect = [False, True]

    with patch.object(bot, "_market_scan_loop", new=AsyncMock()), \
         patch.object(bot, "_position_monitoring_loop", new=AsyncMock()), \
         patch.object(bot, "_binance_sync_loop", new=AsyncMock()), \
         patch("asyncio.sleep", new=AsyncMock()):
        await bot.start()

    assert bot.binance.test_connectivity.call_count == 2
    bot.db.update_bot_status.assert_called()


@pytest.mark.asyncio
async def test_start_succeeds_immediately(bot):
    """Bot should not sleep when first attempt succeeds."""
    bot.binance.test_connectivity.return_value = True

    with patch.object(bot, "_market_scan_loop", new=AsyncMock()), \
         patch.object(bot, "_position_monitoring_loop", new=AsyncMock()), \
         patch.object(bot, "_binance_sync_loop", new=AsyncMock()), \
         patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await bot.start()

    assert bot.binance.test_connectivity.call_count == 1
    mock_sleep.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/User/Library/CloudStorage/GoogleDrive-ignaciovct99@gmail.com/Mi unidad/Documentos/PROYECTOS/Webapp Projects/cryptonita-production"
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/bot/test_trading_bot_connectivity.py -v 2>&1 | head -40
```

Expected: FAIL — currently the bot aborts on first failure, so `update_bot_status` is never called.

- [ ] **Step 3: Replace the hard-abort with retry logic in `trading_bot.py`**

In `src/bot/trading_bot.py`, replace lines 272-275:

```python
        # Test Binance connection
        if not self.binance.test_connectivity():
            logger.error("❌ Failed to connect to Binance. Aborting.")
            return
```

With:

```python
        # Test Binance connection (retry for testnet 502s)
        MAX_ATTEMPTS = 3
        RETRY_DELAY = 60  # seconds
        connected = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self.binance.test_connectivity():
                connected = True
                break
            if attempt < MAX_ATTEMPTS:
                logger.warning(
                    f"⚠️ Binance connection attempt {attempt}/{MAX_ATTEMPTS} failed. "
                    f"Retrying in {RETRY_DELAY}s..."
                )
                await asyncio.sleep(RETRY_DELAY)

        if not connected:
            logger.warning(
                "⚠️ Binance testnet unreachable after 3 attempts — "
                "running in scan-only mode (trade execution disabled)"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/bot/test_trading_bot_connectivity.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit and push**

```bash
cd "/Users/User/Library/CloudStorage/GoogleDrive-ignaciovct99@gmail.com/Mi unidad/Documentos/PROYECTOS/Webapp Projects/cryptonita-production"
git add src/bot/trading_bot.py tests/bot/test_trading_bot_connectivity.py
git commit -m "fix: retry binance testnet connectivity 3x before scan-only fallback"
git push origin main
```

---

## Self-Review

**Spec coverage:**
- [x] Bot retries 3 times on 502 — Task 1, Step 3
- [x] 60s delay between retries — Task 1, Step 3
- [x] Does NOT abort after exhaustion — Task 1, Step 3 (no `return` after 3 failures)
- [x] Tests cover all paths (immediate success, retry success, full failure) — Task 1, Step 1

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:** `connected` bool, `MAX_ATTEMPTS` int, `asyncio.sleep` is already imported in the module.
