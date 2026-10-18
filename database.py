"""Database Manager: SQLite persistence for trades, performance analytics, and dynamic settings.
Follows Clean Architecture with sqlite3.Row dict-like data access and auto-reconnect.
"""

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger("DatabaseManager")


class DatabaseManager:
    def __init__(self, db_path: str = "data/antigravity.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_link_id TEXT UNIQUE NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    tp1_price REAL DEFAULT 0.0,
                    tp2_price REAL DEFAULT 0.0,
                    stop_loss REAL DEFAULT 0.0,
                    exit_price REAL DEFAULT 0.0,
                    result REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'OPEN',
                    tp1_filled INTEGER DEFAULT 0,
                    sl_moved_to_be INTEGER DEFAULT 0,
                    exit_reason TEXT DEFAULT '',
                    note TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    def log_trade(
        self,
        order_link_id: str,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        tp1_price: float = 0.0,
        tp2_price: float = 0.0,
        stop_loss: float = 0.0,
        note: str = ""
    ) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trades (
                    order_link_id, symbol, side, qty, entry_price, tp1_price, tp2_price, stop_loss, status, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
            """, (order_link_id, symbol, side, qty, entry_price, tp1_price, tp2_price, stop_loss, note))
            conn.commit()

    def close_trade(self, order_link_id: str, exit_price: float, result_pnl: float, status: str = "CLOSED", exit_reason: str = "") -> None:
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE trades
                SET status = ?, exit_price = ?, result = ?, exit_reason = ?
                WHERE order_link_id = ?
            """, (status, exit_price, result_pnl, exit_reason, order_link_id))
            conn.commit()

    def mark_tp1_filled_and_be(self, order_link_id: str, remaining_qty: float, partial_pnl: float, be_stop_loss: float) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE trades
                SET tp1_filled = 1, sl_moved_to_be = 1, qty = ?, result = result + ?, stop_loss = ?
                WHERE order_link_id = ?
            """, (remaining_qty, partial_pnl, be_stop_loss, order_link_id))
            conn.commit()

    def mark_be_activated(self, order_link_id: str, be_stop_loss: float) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE trades
                SET sl_moved_to_be = 1, stop_loss = ?
                WHERE order_link_id = ?
            """, (be_stop_loss, order_link_id))
            conn.commit()

    def get_open_trades(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM trades WHERE status = 'OPEN' ORDER BY id DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_trade_by_link_id(self, order_link_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM trades WHERE order_link_id = ?", (order_link_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_today_pnl(self) -> float:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT COALESCE(SUM(result), 0.0) as today_pnl
                FROM trades
                WHERE date(timestamp) = ? AND status != 'OPEN'
            """, (today_str,))
            row = cursor.fetchone()
            return float(row["today_pnl"]) if row else 0.0

    def get_overall_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM trades WHERE status != 'OPEN'")
            closed_trades = [dict(r) for r in cursor.fetchall()]

        total_closed = len(closed_trades)
        if total_closed == 0:
            return {
                "total_closed": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "max_win": 0.0,
                "max_loss": 0.0
            }

        pnls = [float(t["result"]) for t in closed_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        return {
            "total_closed": total_closed,
            "total_pnl": round(sum(pnls), 2),
            "win_rate": round(len(wins) / total_closed * 100.0, 1),
            "max_win": round(max(wins), 2) if wins else 0.0,
            "max_loss": round(min(losses), 2) if losses else 0.0
        }

    def set_setting(self, key: str, value: str) -> None:
        with self._get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return str(row["value"]) if row else default
