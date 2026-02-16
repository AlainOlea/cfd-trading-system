"""
Telegram Notifier Module
=========================
Sends trading signals and alerts via Telegram bot.
Graceful degradation if Telegram is not configured.
"""

import asyncio
import logging

from config.settings import TELEGRAM_ALERTS_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from signals.generator import Signal

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends trading notifications via Telegram bot."""

    def __init__(
        self,
        bot_token: str = TELEGRAM_BOT_TOKEN,
        chat_id: str = TELEGRAM_CHAT_ID,
        enabled: bool = TELEGRAM_ALERTS_ENABLED,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self._bot = None

    @property
    def is_configured(self) -> bool:
        """Check if Telegram credentials are set."""
        return bool(self.bot_token and self.chat_id)

    def _get_bot(self):
        """Lazy-load the Telegram bot."""
        if self._bot is None:
            from telegram import Bot
            self._bot = Bot(token=self.bot_token)
        return self._bot

    def send_signal(self, signal: Signal) -> bool:
        """Send a trading signal via Telegram.

        Args:
            signal: Signal object to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.enabled:
            logger.debug("Telegram alerts disabled in settings")
            return False

        if not self.is_configured:
            logger.warning("Telegram not configured (missing BOT_TOKEN or CHAT_ID)")
            return False

        message = self._format_signal_message(signal)
        return self._send_message(message)

    def send_alert(self, message: str) -> bool:
        """Send a generic alert message via Telegram.

        Args:
            message: Plain text message.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.enabled or not self.is_configured:
            return False
        return self._send_message(message)

    def _send_message(self, text: str) -> bool:
        """Send a message using the Telegram bot (async wrapper)."""
        try:
            bot = self._get_bot()
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode='Markdown',
                ))
            except Exception:
                # Fallback: retry without Markdown if parsing fails
                loop = asyncio.new_event_loop()
                loop.run_until_complete(bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                ))
            finally:
                loop.close()
            logger.info("Telegram message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    @staticmethod
    def _format_signal_message(signal: Signal) -> str:
        """Format a signal as a Markdown message for Telegram.

        Args:
            signal: Signal object.

        Returns:
            Markdown-formatted string.
        """
        if signal.direction == 'HOLD':
            return (
                f"*HOLD* - No action\n"
                f"Strategy: `{signal.strategy}`\n"
                f"Ticker: `{signal.ticker}` ({signal.interval})\n"
                f"Price: ${signal.entry_price:,.2f}\n"
                f"_{signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}_"
            )

        emoji = '🟢' if signal.direction == 'BUY' else '🔴'
        rr = signal.risk_reward_ratio
        rr_str = f"{rr:.1f}" if rr else "N/A"

        lines = [
            f"{emoji} *{signal.direction}* - `{signal.ticker}`",
            f"Strategy: `{signal.strategy}` ({signal.interval})",
            "",
            f"Entry:  `${signal.entry_price:,.2f}`",
            f"SL:     `${signal.stop_loss:,.2f}`",
            f"TP:     `${signal.take_profit:,.2f}`",
            f"R/R:    `{rr_str}`",
            f"Conf:   `{signal.confidence:.0%}`",
        ]

        if signal.ml_filtered:
            ml_conf = f"{signal.ml_confidence:.0%}" if signal.ml_confidence else "N/A"
            lines.append(f"ML:     `{ml_conf}`")

        lines.append(f"\n_{signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}_")

        return "\n".join(lines)
