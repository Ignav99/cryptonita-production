"""
TELEGRAM NOTIFIER
==================
Async Telegram notifications for trade events, errors, and alerts.
"""

import httpx
from typing import Optional
from loguru import logger


class TelegramNotifier:
    """Sends notifications to Telegram via Bot API."""

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)
        if self.enabled:
            logger.info("Telegram notifications enabled")

    async def send(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message to Telegram. Returns True if sent."""
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    self.BASE_URL.format(token=self.token),
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True,
                    },
                )
                if resp.status_code != 200:
                    logger.warning(f"Telegram send failed: {resp.status_code}")
                    return False
                return True
        except Exception as e:
            logger.warning(f"Telegram error: {e}")
            return False

    async def notify_trade(self, action: str, ticker: str, price: float,
                           quantity: float, usd_value: float,
                           confidence: str = "", probability: float = 0.0,
                           pnl: float = 0.0, reason: str = ""):
        """Notify about a trade execution."""
        if action == "BUY":
            msg = (
                f"<b>BUY {ticker}</b>\n"
                f"Price: ${price:.4f}\n"
                f"Size: ${usd_value:.2f} ({quantity:.4f})\n"
                f"Confidence: {confidence} (p={probability:.3f})"
            )
        else:
            emoji = "+" if pnl >= 0 else ""
            msg = (
                f"<b>SELL {ticker}</b>\n"
                f"Price: ${price:.4f}\n"
                f"Size: ${usd_value:.2f}\n"
                f"P&L: {emoji}${pnl:.2f}\n"
                f"Reason: {reason}"
            )
        await self.send(msg)

    async def notify_circuit_breaker(self, drawdown_pct: float, action: str):
        """Notify about circuit breaker activation."""
        msg = (
            f"<b>CIRCUIT BREAKER</b>\n"
            f"Drawdown: {drawdown_pct:.1f}%\n"
            f"Action: {action}"
        )
        await self.send(msg)

    async def notify_error(self, error: str, context: str = ""):
        """Notify about a critical error."""
        msg = f"<b>ERROR</b>\n{context}\n<code>{error[:500]}</code>"
        await self.send(msg)

    async def notify_model_promoted(self, version: int, sharpe: float, win_rate: float):
        """Notify about model promotion."""
        msg = (
            f"<b>MODEL PROMOTED v{version}</b>\n"
            f"Sharpe: {sharpe:.2f}\n"
            f"Win Rate: {win_rate:.1f}%"
        )
        await self.send(msg)

    async def notify_daily_summary(self, portfolio_value: float, daily_pnl: float,
                                   open_positions: int, trades_today: int):
        """Daily P&L summary."""
        emoji = "+" if daily_pnl >= 0 else ""
        msg = (
            f"<b>DAILY SUMMARY</b>\n"
            f"Portfolio: ${portfolio_value:.2f}\n"
            f"Day P&L: {emoji}${daily_pnl:.2f}\n"
            f"Open positions: {open_positions}\n"
            f"Trades today: {trades_today}"
        )
        await self.send(msg)
