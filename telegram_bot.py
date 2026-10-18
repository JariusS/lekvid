"""Telegram Bot UI Controller (AntiGravity 2.0 pattern).
Provides full interactive control over the trading bot:
- Persistent ReplyKeyboardMarkup: [💼 Открытые сделки], [💰 Баланс], [📊 Статистика], [⚙️ Настройки], [🚨 Закрыть всё], [⚙️ Статус], [📈 График PnL]
- InlineKeyboardMarkup: [🛡 В безубыток], [🎯 Забрать 50%], [❌ Закрыть], [📈 График Bybit]
- Settings: Auto / Long Only / Short Only / Toggle Pause
- Panic Confirmation workflow
- Background polling daemon thread
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
import time
from typing import Optional

from telebot import TeleBot
from telebot.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from config import settings
from data_ingestion import MarketDataIngestor
from database import DatabaseManager
from execution_engine import BaseExecutionEngine
from models import TradingSignal
from version import __version__

logger = logging.getLogger("TelegramBotUI")


class TelegramBotUI:
    def __init__(
        self,
        db: DatabaseManager,
        engine: BaseExecutionEngine,
        bot_token: str = settings.TELEGRAM_BOT_TOKEN or "",
        chat_id: str = settings.TELEGRAM_CHAT_ID or ""
    ):
        self.db = db
        self.engine = engine
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.is_configured = bool(self.bot_token and self.chat_id)
        self.is_paused = False
        self.trade_mode = "AUTO"  # "AUTO", "LONG_ONLY", "SHORT_ONLY"
        self.active_symbol = settings.DEFAULT_SYMBOL
        self.ingestor = MarketDataIngestor()
        self._cached_top_coins = []
        self._top_coins_last_updated = 0.0
        self._top_cache_ttl = 900.0  # 15 minutes TTL

        if not self.is_configured:
            return

        self.bot = TeleBot(self.bot_token, parse_mode="HTML")
        self._register_handlers()

        # Start non-blocking polling thread
        self.poll_thread = threading.Thread(target=self._start_polling, daemon=True)
        self.poll_thread.start()

    def _get_dynamic_top_10(self, force_refresh: bool = False) -> list:
        now = time.time()
        if not force_refresh and self._cached_top_coins and (now - self._top_coins_last_updated) < self._top_cache_ttl:
            return self._cached_top_coins

        try:
            fresh = self.ingestor.fetch_top_linear_tickers(limit=10, min_turnover=50_000_000.0)
            if fresh:
                self._cached_top_coins = fresh
                self._top_coins_last_updated = now
        except Exception as e:
            logger.error(f"Error refreshing dynamic top 10: {e}")

        return self._cached_top_coins

    def _start_polling(self) -> None:
        while True:
            try:
                self.bot.infinity_polling(logger_level=logging.ERROR, timeout=20)
                break
            except Exception as e:
                logger.error(f"Telegram polling exception: {e}. Reconnecting in 10s...")
                time.sleep(10)

    def _is_auth(self, message: Message) -> bool:
        return str(message.chat.id) == self.chat_id

    def _get_menu_keyboard(self) -> ReplyKeyboardMarkup:
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row(KeyboardButton("💼 Открытые сделки"), KeyboardButton("💰 Баланс"))
        markup.row(KeyboardButton("📊 Статистика"), KeyboardButton("🏆 Топ монет"))
        markup.row(KeyboardButton("⚙️ Настройки"), KeyboardButton("🚨 Закрыть всё"))
        markup.row(KeyboardButton("🔄 Синхронизация Sheets"), KeyboardButton("⚙️ Статус"))
        return markup

    @staticmethod
    def _build_progress_bar(entry: float, current: float, target: float, side: str) -> str:
        total_dist = abs(target - entry)
        if total_dist <= 0:
            return "[░░░░░░░░░░] 0%"
        cur_dist = (current - entry) if side in ["Buy", "LONG"] else (entry - current)
        ratio = max(0.0, min(1.0, cur_dist / total_dist))
        filled = int(round(ratio * 10))
        bar = "▓" * filled + "░" * (10 - filled)
        return f"[{bar}] {int(ratio * 100)}% к TP1"

    def _register_handlers(self) -> None:

        @self.bot.message_handler(commands=['start', 'menu'])
        def cmd_start(msg: Message):
            if not self._is_auth(msg): return
            text = (
                f"🤖 <b>Antigravity Liquidity Sweep Bot v{__version__}</b>\n\n"
                "Система активна и отслеживает кластеры ликвидности.\n"
                "Используйте кнопки меню внизу для управления:"
            )
            self.bot.send_message(msg.chat.id, text, reply_markup=self._get_menu_keyboard())

        @self.bot.message_handler(commands=['balance'])
        def cmd_balance(msg: Message):
            if not self._is_auth(msg): return
            bal = self.engine.get_balance()
            today_pnl = self.db.get_today_pnl()
            text = (
                f"💰 <b>Кошелек & Баланс:</b>\n\n"
                f"• Доступный баланс: <b>${bal:,.2f} USDT</b>\n"
                f"• PnL за сегодня: <b>{today_pnl:+.2f} USDT</b>\n"
                f"• Режим исполнения: <code>{'DRY-RUN (Симуляция)' if bal > 50000 else 'LIVE TRADING'}</code>"
            )
            self.bot.send_message(msg.chat.id, text)

        @self.bot.message_handler(commands=['status'])
        def cmd_status(msg: Message):
            if not self._is_auth(msg): return
            status_icon = "⏸ ПАУЗА" if self.is_paused else "🟢 АКТИВЕН"
            open_count = len(self.db.get_open_trades())
            text = (
                f"⚙️ <b>Статус торговой системы:</b>\n\n"
                f"• Версия: <b>v{__version__}</b>\n"
                f"• Состояние сканера: <b>{status_icon}</b>\n"
                f"• Направление торговли: <b>{self.trade_mode}</b>\n"
                f"• Плечо: <b>{settings.MAX_LEVERAGE}x (СТРОГО x1)</b>\n"
                f"• Открытых позиций: <b>{open_count}</b>\n"
                f"• Рабочая пара: <code>{settings.DEFAULT_SYMBOL}</code> [{settings.TIMEFRAME}]\n"
                f"• Стратегия: <i>Liquidity Sweep & Reclaim</i>\n"
                f"• Риск на сделку: <b>{settings.MAX_RISK_PER_TRADE_PCT*100:.1f}%</b>"
            )
            self.bot.send_message(msg.chat.id, text)

        @self.bot.message_handler(commands=['stats'])
        def cmd_stats(msg: Message):
            if not self._is_auth(msg): return
            today_pnl = self.db.get_today_pnl()
            stats = self.db.get_overall_stats()
            text = (
                f"📊 <b>Статистика торговли:</b>\n\n"
                f"• PnL сегодня: <b>{today_pnl:+.2f} USDT</b>\n"
                f"• Всего закрыто сделок: <b>{stats['total_closed']}</b>\n"
                f"• WinRate: <b>{stats['win_rate']:.1f}%</b>\n"
                f"• Суммарный PnL: <b>{stats['total_pnl']:+.2f} USDT</b>\n"
                f"• Лучший трейд: <b>+{stats['max_win']:.2f} USDT</b>\n"
                f"• Худший трейд: <b>{stats['max_loss']:.2f} USDT</b>"
            )
            self.bot.send_message(msg.chat.id, text)

        @self.bot.message_handler(commands=['open'])
        def cmd_open(msg: Message):
            if not self._is_auth(msg): return
            trades = self.db.get_open_trades()
            if not trades:
                self.bot.send_message(msg.chat.id, "📉 <b>Нет активных открытых позиций.</b>")
                return

            for t in trades:
                sym = t['symbol']
                entry_p = float(t['entry_price'])
                side = t['side']
                link_id = t['order_link_id']
                tp1 = float(t.get('tp1_price', 0.0))
                sl = float(t.get('stop_loss', 0.0))

                cur_p = self.engine.get_ticker_price(sym) or entry_p
                direction = 1.0 if side in ['Buy', 'LONG'] else -1.0
                pnl = (cur_p - entry_p) * float(t['qty']) * direction
                pnl_pct = ((cur_p - entry_p) / entry_p) * 100.0 * direction

                icon = "🟢 LONG" if side in ['Buy', 'LONG'] else "🔴 SHORT"
                pnl_sign = "🟢" if pnl >= 0 else "🔴"
                progress = self._build_progress_bar(entry_p, cur_p, tp1, side)

                text = (
                    f"{pnl_sign} <b>{sym} ({icon})</b>\n"
                    f"Вход: <b>${entry_p:,.2f}</b> → Сейчас: <b>${cur_p:,.2f}</b>\n"
                    f"Стоп-лосс: <b>${sl:,.2f}</b> | TP1: <b>${tp1:,.2f}</b>\n"
                    f"💵 PnL: <b>{pnl:+.2f} USDT ({pnl_pct:+.2f}%)</b>\n"
                    f"🎯 Прогресс: <code>{progress}</code>"
                )

                markup = InlineKeyboardMarkup()
                markup.row(
                    InlineKeyboardButton("🛡 В безубыток", callback_data=f"be_{link_id}"),
                    InlineKeyboardButton("🎯 Забрать 50%", callback_data=f"part_{link_id}")
                )
                markup.row(
                    InlineKeyboardButton("❌ Закрыть позицию", callback_data=f"close_{link_id}"),
                    InlineKeyboardButton("📈 График Bybit", url=f"https://www.bybit.com/trade/usdt/{sym}")
                )
                self.bot.send_message(msg.chat.id, text, reply_markup=markup)

        @self.bot.message_handler(commands=['settings'])
        def cmd_settings(msg: Message):
            if not self._is_auth(msg): return
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("🔄 АВТО (Оба направления)", callback_data="mode_AUTO"),
                InlineKeyboardButton("🟢 Только LONG", callback_data="mode_LONG_ONLY")
            )
            markup.row(
                InlineKeyboardButton("🔴 Только SHORT", callback_data="mode_SHORT_ONLY"),
                InlineKeyboardButton("⏸ Пауза/Старт", callback_data="toggle_pause")
            )
            text = (
                f"⚙️ <b>Панель управления настройками:</b>\n\n"
                f"• Текущий режим: <b>{self.trade_mode}</b>\n"
                f"• Статус сканера: <b>{'ПАУЗА ⏸' if self.is_paused else 'АКТИВЕН ▶️'}</b>\n\n"
                f"Выберите действие кнопками ниже:"
            )
            self.bot.send_message(msg.chat.id, text, reply_markup=markup)

        @self.bot.message_handler(commands=['panic'])
        def cmd_panic(msg: Message):
            if not self._is_auth(msg): return
            trades = self.db.get_open_trades()
            count = len(trades)
            if count == 0:
                self.bot.send_message(msg.chat.id, "ℹ️ <b>Нет открытых позиций для закрытия.</b>")
                return

            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("🚨 ДА, ЗАКРЫТЬ ВСЁ", callback_data="panic_confirm"),
                InlineKeyboardButton("Отмена", callback_data="panic_cancel")
            )
            self.bot.send_message(
                msg.chat.id,
                f"⚠️ <b>ВНИМАНИЕ! Экстренное закрытие!</b>\nЗакрыть все <b>{count}</b> позиций по рынку и поставить сканер на паузу?",
                reply_markup=markup
            )

        @self.bot.message_handler(commands=['top'])
        def cmd_top(msg: Message):
            if not self._is_auth(msg): return
            coins = self._get_dynamic_top_10()
            now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

            lines = [
                "🏆 <b>Топ-10 монет Bybit V5 (Авто-обновление каждые 15 мин):</b>",
                "<i>Критерии: оборот > $50M, деривативный интерес, внутридневная волатильность.</i>\n"
            ]

            markup = InlineKeyboardMarkup()
            # Top row quick select buttons
            row_buttons = []
            for i, c in enumerate(coins[:10], start=1):
                sym = c["symbol"]
                turnover_m = c["turnover"] / 1_000_000
                p = c["last_price"]
                v = c["volatility_pct"]
                chg = c["change_24h_pct"]
                chg_icon = "🟢" if chg >= 0 else "🔴"
                is_active = " ⭐" if sym == self.active_symbol else ""

                price_fmt = f"${p:,.4f}" if p < 1.0 else f"${p:,.2f}"
                lines.append(
                    f"<b>{i:2d}. {sym}{is_active}</b>\n"
                    f"   • Цена: <b>{price_fmt}</b> ({chg_icon} {chg:+.2f}%)\n"
                    f"   • Оборот 24h: <b>${turnover_m:,.1f}M</b> | Волатильность: <b>{v:.2f}%</b>"
                )

            lines.append(f"\n🕒 Данные актуальны на: <code>{now_str}</code>")
            lines.append(f"🎯 Текущая рабочая пара бота: <code>{self.active_symbol}</code>")

            # Inline switcher for top 3 and refresh
            markup.row(
                InlineKeyboardButton("⚡ BTC", callback_data="select_sym_BTCUSDT"),
                InlineKeyboardButton("⚡ ETH", callback_data="select_sym_ETHUSDT"),
                InlineKeyboardButton("⚡ SOL", callback_data="select_sym_SOLUSDT")
            )
            markup.row(
                InlineKeyboardButton("⚡ NEAR", callback_data="select_sym_NEARUSDT"),
                InlineKeyboardButton("⚡ XRP", callback_data="select_sym_XRPUSDT"),
                InlineKeyboardButton("⚡ DOGE", callback_data="select_sym_DOGEUSDT")
            )
            markup.row(
                InlineKeyboardButton("🔄 Обновить сейчас (Кэш 15м)", callback_data="refresh_top")
            )

            self.bot.send_message(msg.chat.id, "\n".join(lines), reply_markup=markup)

        @self.bot.message_handler(commands=['sync_sheets'])
        def cmd_sync_sheets(msg: Message):
            if not self._is_auth(msg): return
            self.bot.send_message(
                msg.chat.id,
                "🔄 <b>Google Sheets:</b>\n"
                "Автоматическая выгрузка настроена при закрытии сделок в локальную БД SQLite (<code>data/antigravity.db</code>)."
            )

        # --- Inline Callbacks ---
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("be_"))
        def callback_be(call: CallbackQuery):
            if str(call.message.chat.id) != self.chat_id: return
            link_id = call.data.replace("be_", "")
            self.bot.answer_callback_query(call.id, "Переношу стоп в БУ...")
            trade = self.db.get_trade_by_link_id(link_id)
            if trade:
                be_price = trade['entry_price']
                self.db.mark_be_activated(link_id, be_price)
                self.bot.send_message(call.message.chat.id, f"🛡 <b>Стоп-лосс для {trade['symbol']} перенесен в безубыток: ${be_price:,.2f}</b>")

        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("part_"))
        def callback_part(call: CallbackQuery):
            if str(call.message.chat.id) != self.chat_id: return
            link_id = call.data.replace("part_", "")
            self.bot.answer_callback_query(call.id, "Фиксирую 50%...")
            trade = self.db.get_trade_by_link_id(link_id)
            if trade:
                half_qty = round(float(trade['qty']) * 0.5, 4)
                cur_price = self.engine.get_ticker_price(trade['symbol']) or float(trade['entry_price'])
                direction = 1.0 if trade['side'] in ['Buy', 'LONG'] else -1.0
                partial_pnl = (cur_price - float(trade['entry_price'])) * half_qty * direction
                self.engine.close_position(trade['symbol'], half_qty, trade['side'])
                self.db.mark_tp1_filled_and_be(link_id, half_qty, partial_pnl, trade['entry_price'])
                self.bot.send_message(
                    call.message.chat.id,
                    f"🎯 <b>Зафиксировано 50% объема по {trade['symbol']}!</b>\n💵 Зафиксированный PnL: <b>{partial_pnl:+.2f} USDT</b>"
                )

        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("close_"))
        def callback_close(call: CallbackQuery):
            if str(call.message.chat.id) != self.chat_id: return
            link_id = call.data.replace("close_", "")
            self.bot.answer_callback_query(call.id, "Закрываю позицию...")
            trade = self.db.get_trade_by_link_id(link_id)
            if trade:
                cur_price = self.engine.get_ticker_price(trade['symbol']) or float(trade['entry_price'])
                direction = 1.0 if trade['side'] in ['Buy', 'LONG'] else -1.0
                total_pnl = (cur_price - float(trade['entry_price'])) * float(trade['qty']) * direction
                self.engine.close_position(trade['symbol'], float(trade['qty']), trade['side'])
                self.db.close_trade(link_id, cur_price, total_pnl, status="CLOSED_MANUAL", exit_reason="MANUAL_CLOSE")
                self.bot.send_message(
                    call.message.chat.id,
                    f"❌ <b>Позиция {trade['symbol']} полностью закрыта по рынку!</b>\nИтоговый PnL: <b>{total_pnl:+.2f} USDT</b>"
                )

        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("mode_"))
        def callback_mode(call: CallbackQuery):
            if str(call.message.chat.id) != self.chat_id: return
            new_mode = call.data.replace("mode_", "")
            self.trade_mode = new_mode
            self.db.set_setting("trade_mode", new_mode)
            self.bot.answer_callback_query(call.id, f"Режим изменен: {new_mode}")
            self.bot.send_message(call.message.chat.id, f"✅ <b>Режим торговли переключен:</b> <code>{new_mode}</code>")

        @self.bot.callback_query_handler(func=lambda c: c.data == "toggle_pause")
        def callback_toggle_pause(call: CallbackQuery):
            if str(call.message.chat.id) != self.chat_id: return
            self.is_paused = not self.is_paused
            state_text = "⏸ НА ПАУЗЕ" if self.is_paused else "▶️ ВОЗОБНОВЛЕН"
            self.bot.answer_callback_query(call.id, state_text)
            self.bot.send_message(call.message.chat.id, f"⚙️ Сканер теперь: <b>{state_text}</b>")

        @self.bot.callback_query_handler(func=lambda c: c.data == "panic_confirm")
        def callback_panic_confirm(call: CallbackQuery):
            if str(call.message.chat.id) != self.chat_id: return
            self.is_paused = True
            trades = self.db.get_open_trades()
            closed_count = 0
            for t in trades:
                cur_price = self.engine.get_ticker_price(t['symbol']) or float(t['entry_price'])
                direction = 1.0 if t['side'] in ['Buy', 'LONG'] else -1.0
                pnl = (cur_price - float(t['entry_price'])) * float(t['qty']) * direction
                self.engine.close_position(t['symbol'], float(t['qty']), t['side'])
                self.db.close_trade(t['order_link_id'], cur_price, pnl, status="CLOSED_PANIC", exit_reason="PANIC_BUTTON")
                closed_count += 1
            self.bot.answer_callback_query(call.id, f"Закрыто {closed_count} сделок!")
            self.bot.send_message(call.message.chat.id, f"🚨 <b>ЭКСТРЕННАЯ ПАНИКА:</b> Все позиции ({closed_count}) закрыты, бот поставлен на паузу.")

        @self.bot.callback_query_handler(func=lambda c: c.data == "panic_cancel")
        def callback_panic_cancel(call: CallbackQuery):
            if str(call.message.chat.id) != self.chat_id: return
            self.bot.answer_callback_query(call.id, "Отменено")
            self.bot.send_message(call.message.chat.id, "✅ Экстренное закрытие отменено.")

        @self.bot.callback_query_handler(func=lambda c: c.data == "refresh_top")
        def callback_refresh_top(call: CallbackQuery):
            if str(call.message.chat.id) != self.chat_id: return
            self.bot.answer_callback_query(call.id, "Обновляю данные с Bybit...")
            coins = self._get_dynamic_top_10(force_refresh=True)
            now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
            lines = [
                "🏆 <b>Топ-10 монет Bybit V5 (Обновлено):</b>",
                "<i>Критерии: оборот > $50M, деривативный интерес, внутридневная волатильность.</i>\n"
            ]
            for i, c in enumerate(coins[:10], start=1):
                sym = c["symbol"]
                turnover_m = c["turnover"] / 1_000_000
                p = c["last_price"]
                v = c["volatility_pct"]
                chg = c["change_24h_pct"]
                chg_icon = "🟢" if chg >= 0 else "🔴"
                is_active = " ⭐" if sym == self.active_symbol else ""
                price_fmt = f"${p:,.4f}" if p < 1.0 else f"${p:,.2f}"
                lines.append(
                    f"<b>{i:2d}. {sym}{is_active}</b>\n"
                    f"   • Цена: <b>{price_fmt}</b> ({chg_icon} {chg:+.2f}%)\n"
                    f"   • Оборот 24h: <b>${turnover_m:,.1f}M</b> | Волатильность: <b>{v:.2f}%</b>"
                )
            lines.append(f"\n🕒 Данные актуальны на: <code>{now_str}</code>")
            lines.append(f"🎯 Текущая рабочая пара бота: <code>{self.active_symbol}</code>")

            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("⚡ BTC", callback_data="select_sym_BTCUSDT"),
                InlineKeyboardButton("⚡ ETH", callback_data="select_sym_ETHUSDT"),
                InlineKeyboardButton("⚡ SOL", callback_data="select_sym_SOLUSDT")
            )
            markup.row(
                InlineKeyboardButton("⚡ NEAR", callback_data="select_sym_NEARUSDT"),
                InlineKeyboardButton("⚡ XRP", callback_data="select_sym_XRPUSDT"),
                InlineKeyboardButton("⚡ DOGE", callback_data="select_sym_DOGEUSDT")
            )
            markup.row(
                InlineKeyboardButton("🔄 Обновить сейчас (Кэш 15м)", callback_data="refresh_top")
            )
            try:
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="\n".join(lines),
                    reply_markup=markup
                )
            except Exception:
                pass

        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("select_sym_"))
        def callback_select_symbol(call: CallbackQuery):
            if str(call.message.chat.id) != self.chat_id: return
            new_sym = call.data.replace("select_sym_", "")
            self.active_symbol = new_sym
            self.db.set_setting("active_symbol", new_sym)
            self.bot.answer_callback_query(call.id, f"Выбрана пара: {new_sym}")
            self.bot.send_message(
                call.message.chat.id,
                f"✅ <b>Активная торговая пара переключена:</b> <code>{new_sym}</code>\n"
                f"Сканер ликвидности ориентирован на поиск свипов по {new_sym}."
            )

        # --- Text buttons routing ---
        @self.bot.message_handler(func=lambda m: True)
        def handle_text_menu(msg: Message):
            if not self._is_auth(msg): return
            text = msg.text
            if text == "💼 Открытые сделки":
                cmd_open(msg)
            elif text == "💰 Баланс":
                cmd_balance(msg)
            elif text == "📊 Статистика":
                cmd_stats(msg)
            elif text == "🏆 Топ монет":
                cmd_top(msg)
            elif text == "⚙️ Настройки":
                cmd_settings(msg)
            elif text == "🚨 Закрыть всё":
                cmd_panic(msg)
            elif text == "🔄 Синхронизация Sheets":
                cmd_sync_sheets(msg)
            elif text == "⚙️ Статус":
                cmd_status(msg)

    def send_message(self, text: str) -> None:
        """Standard thread-safe notification sender matching TELEGRAM_BOT_GUIDE."""
        self.send_notification(text)

    def send_notification(self, text: str) -> None:
        """Thread-safe notification dispatcher for trading engine."""
        if not self.is_configured:
            return
        try:
            self.bot.send_message(self.chat_id, text)
        except Exception as e:
            logger.error(f"Failed to transmit Telegram message: {e}")

    def notify_signal(self, signal: TradingSignal, order_id: str, units: float) -> None:
        if not self.is_configured:
            return
        side_icon = "🟢 LONG" if signal.side.value == "LONG" else "🔴 SHORT"
        text = (
            f"⚡ <b>LIQUIDITY SWEEP & RECLAIM DETECTED</b>\n\n"
            f"• Монета: <b>{signal.symbol}</b> ({side_icon})\n"
            f"• Вход: <b>${signal.entry_price:,.2f}</b>\n"
            f"• Стоп-лосс: <b>${signal.stop_loss:,.2f}</b>\n"
            f"• Тейк TP1 (VWAP): <b>${signal.tp1_price:,.2f}</b>\n"
            f"• Тейк TP2: <b>${signal.tp2_price:,.2f}</b>\n"
            f"• Плечо: <b>{signal.calculated_leverage}x</b>\n"
            f"• Объем: <b>{signal.volume_ratio:.2f}x SMA20</b>\n"
            f"• Ордер ID: <code>{order_id}</code>\n"
            f"• Размер: <b>{units} units</b>\n\n"
            f"<i>{signal.rationale}</i>"
        )
        self.send_notification(text)
