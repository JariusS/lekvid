"""Notifier: Async Telegram notification dispatcher.
Transmits execution alerts, trade triggers, and backtest summaries with attached chart artifacts.
"""

import asyncio
from pathlib import Path
from typing import Optional
import aiohttp

from config import settings
from models import BacktestSummary, TradingSignal


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str = settings.TELEGRAM_BOT_TOKEN or "",
        chat_id: str = settings.TELEGRAM_CHAT_ID or ""
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def send_message(self, text: str) -> bool:
        if not self.is_configured:
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return resp.status == 200

    async def send_photo(self, photo_path: str, caption: str = "") -> bool:
        if not self.is_configured or not Path(photo_path).exists():
            return False

        url = f"{self.base_url}/sendPhoto"
        data = aiohttp.FormData()
        data.add_field("chat_id", self.chat_id)
        data.add_field("caption", caption)
        data.add_field("parse_mode", "Markdown")
        data.add_field("photo", open(photo_path, "rb"), filename=Path(photo_path).name)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return resp.status == 200

    def format_signal_message(self, signal: TradingSignal) -> str:
        return (
            f"⚡ *LIQUIDITY SWEEP & RECLAIM DETECTED*\n"
            f"• *Symbol:* `{signal.symbol}`\n"
            f"• *Side:* `{signal.side.value}`\n"
            f"• *Entry:* ${signal.entry_price:,.2f}\n"
            f"• *Stop-Loss:* ${signal.stop_loss:,.2f}\n"
            f"• *TP1 (VWAP):* ${signal.tp1_price:,.2f}\n"
            f"• *TP2 (Cluster):* ${signal.tp2_price:,.2f}\n"
            f"• *Leverage:* `{signal.calculated_leverage}x`\n"
            f"• *Volume Ratio:* `{signal.volume_ratio}x SMA20`\n"
            f"• *Funding Rate:* `{signal.funding_rate*100:.4f}%`\n"
            f"• *Rationale:* _{signal.rationale}_"
        )

    def format_summary_message(self, summary: BacktestSummary) -> str:
        return (
            f"📊 *BACKTEST & STRESS-TEST VERDICT*\n"
            f"• *Symbol:* `{summary.symbol}` [{summary.timeframe}]\n"
            f"• *Final Equity:* ${summary.final_balance:,.2f} (Initial: ${summary.initial_balance:,.2f})\n"
            f"• *Trades:* `{summary.total_trades}` | *Win Rate:* `{summary.win_rate*100:.1f}%`\n"
            f"• *Sharpe:* `{summary.sharpe_ratio:.2f}` | *Sortino:* `{summary.sortino_ratio:.2f}`\n"
            f"• *Max Drawdown:* `{summary.max_drawdown_pct*100:.2f}%`\n"
            f"• *VaR 95%:* `{summary.var_95*100:.2f}%` | *Expected Shortfall:* `{summary.expected_shortfall*100:.2f}%`\n"
            f"• *PBO Overfitting Score:* `{summary.pbo_score:.2f}`\n"
            f"• *Pre-Flight Tests:* `{'PASSED ✅' if summary.unit_tests_passed else 'FAILED ❌'}`"
        )