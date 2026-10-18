"""Execution Engine: Decoupled order routing for Bybit V5 Perpetual Futures.
Adheres strictly to Uncle Bob's Clean Code:
- Zero flag arguments: distinct LiveExecutionEngine vs SimulatedExecutionEngine classes.
- Command-Query Separation (CQS): commands mutate or dispatch, queries return status.
- Secure HMAC-SHA256 signing for Bybit V5 REST endpoints.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional
import requests

from config import settings
from models import ExecutionError, OrderStatus, SignalSide, TradingSignal


class BaseExecutionEngine(ABC):
    @abstractmethod
    def submit_order(self, signal: TradingSignal, quantity_units: float) -> str:
        pass

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> None:
        pass

    @abstractmethod
    def get_balance(self) -> float:
        pass

    @abstractmethod
    def get_ticker_price(self, symbol: str) -> float:
        pass

    @abstractmethod
    def close_position(self, symbol: str, qty: float, side: str) -> str:
        pass


class SimulatedExecutionEngine(BaseExecutionEngine):
    def __init__(self, latency_ms: int = settings.EXECUTION_LATENCY_MS):
        self.latency_ms = latency_ms
        self.orders: Dict[str, Dict[str, Any]] = {}
        self._order_counter = 1000
        self.simulated_balance = 100_000.0

    def get_balance(self) -> float:
        return self.simulated_balance

    def get_ticker_price(self, symbol: str) -> float:
        try:
            url = "https://api.bybit.com/v5/market/tickers"
            resp = requests.get(url, params={"category": "linear", "symbol": symbol}, timeout=5)
            list_items = resp.json().get("result", {}).get("list", [])
            if list_items:
                return float(list_items[0].get("lastPrice", 0.0))
        except Exception:
            pass
        return 82000.0 if "BTC" in symbol else (2400.0 if "ETH" in symbol else 100.0)

    def close_position(self, symbol: str, qty: float, side: str) -> str:
        self._order_counter += 1
        return f"SIM-CLOSE-{self._order_counter}"

    def submit_order(self, signal: TradingSignal, quantity_units: float) -> str:
        self._order_counter += 1
        order_id = f"SIM-{self._order_counter}"
        self.orders[order_id] = {
            "order_id": order_id,
            "symbol": signal.symbol,
            "side": signal.side.value,
            "price": signal.entry_price,
            "qty": quantity_units,
            "status": OrderStatus.FILLED,
            "created_at": datetime.now(timezone.utc),
        }
        return order_id

    def cancel_order(self, symbol: str, order_id: str) -> None:
        if order_id in self.orders:
            self.orders[order_id]["status"] = OrderStatus.CANCELLED

    def get_order_status(self, symbol: str, order_id: str) -> OrderStatus:
        order = self.orders.get(order_id)
        if not order:
            return OrderStatus.REJECTED
        return order["status"]


class LiveExecutionEngine(BaseExecutionEngine):
    def __init__(
        self,
        api_key: str = settings.BYBIT_API_KEY,
        api_secret: str = settings.BYBIT_API_SECRET,
        testnet: bool = settings.BYBIT_TESTNET
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"
        self.recv_window = "5000"

    def _generate_signature(self, timestamp: str, payload_str: str) -> str:
        param_str = f"{timestamp}{self.api_key}{self.recv_window}{payload_str}"
        return hmac.new(
            self.api_secret.encode("utf-8"),
            param_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def _get_headers(self, timestamp: str, signature: str) -> Dict[str, str]:
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.recv_window,
            "Content-Type": "application/json",
        }

    def submit_order(self, signal: TradingSignal, quantity_units: float) -> str:
        if not self.api_key or not self.api_secret:
            raise ExecutionError("Cannot execute live order: Bybit API credentials missing in environment.")

        endpoint = f"{self.base_url}/v5/order/create"
        timestamp = str(int(time.time() * 1000))
        bybit_side = "Buy" if signal.side == SignalSide.LONG else "Sell"

        payload = {
            "category": "linear",
            "symbol": signal.symbol,
            "side": bybit_side,
            "orderType": "Market",
            "qty": str(quantity_units),
            "stopLoss": str(signal.stop_loss),
            "takeProfit": str(signal.tp1_price),
            "timeInForce": "GTC",
            "positionIdx": 0,
        }
        body_str = json.dumps(payload)
        signature = self._generate_signature(timestamp, body_str)
        headers = self._get_headers(timestamp, signature)

        try:
            resp = requests.post(endpoint, headers=headers, data=body_str, timeout=5)
            resp.raise_for_status()
            res_json = resp.json()
            if res_json.get("retCode") != 0:
                raise ExecutionError(f"Bybit rejected order: {res_json.get('retMsg')} (code {res_json.get('retCode')})")
            return res_json.get("result", {}).get("orderId", "")
        except Exception as exc:
            raise ExecutionError(f"Live order transmission failed: {exc}") from exc

    def cancel_order(self, symbol: str, order_id: str) -> None:
        endpoint = f"{self.base_url}/v5/order/cancel"
        timestamp = str(int(time.time() * 1000))
        payload = {"category": "linear", "symbol": symbol, "orderId": order_id}
        body_str = json.dumps(payload)
        signature = self._generate_signature(timestamp, body_str)
        headers = self._get_headers(timestamp, signature)
        
        try:
            resp = requests.post(endpoint, headers=headers, data=body_str, timeout=5)
            resp.raise_for_status()
        except Exception as exc:
            raise ExecutionError(f"Failed to cancel Bybit order {order_id}: {exc}") from exc

    def get_order_status(self, symbol: str, order_id: str) -> OrderStatus:
        endpoint = f"{self.base_url}/v5/order/realtime"
        timestamp = str(int(time.time() * 1000))
        query_str = f"category=linear&symbol={symbol}&orderId={order_id}"
        signature = self._generate_signature(timestamp, query_str)
        headers = self._get_headers(timestamp, signature)

        try:
            resp = requests.get(f"{endpoint}?{query_str}", headers=headers, timeout=5)
            resp.raise_for_status()
            orders = resp.json().get("result", {}).get("list", [])
            if not orders:
                return OrderStatus.REJECTED
            bybit_status = orders[0].get("orderStatus")
            status_map = {
                "Created": OrderStatus.PENDING,
                "New": OrderStatus.PENDING,
                "Filled": OrderStatus.FILLED,
                "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
                "Cancelled": OrderStatus.CANCELLED,
            }
            return status_map.get(bybit_status, OrderStatus.REJECTED)
        except Exception as exc:
            raise ExecutionError(f"Failed to query Bybit order status: {exc}") from exc

    def get_balance(self) -> float:
        endpoint = f"{self.base_url}/v5/account/wallet-balance"
        timestamp = str(int(time.time() * 1000))
        query_str = "accountType=UNIFIED"
        signature = self._generate_signature(timestamp, query_str)
        headers = self._get_headers(timestamp, signature)
        try:
            resp = requests.get(f"{endpoint}?{query_str}", headers=headers, timeout=5)
            list_res = resp.json().get("result", {}).get("list", [])
            if list_res:
                coins = list_res[0].get("coin", [])
                for c in coins:
                    if c.get("coin") == "USDT":
                        return float(c.get("walletBalance", 0.0))
                return float(list_res[0].get("totalWalletBalance", 0.0))
        except Exception:
            pass
        return 0.0

    def get_ticker_price(self, symbol: str) -> float:
        try:
            url = f"{self.base_url}/v5/market/tickers"
            resp = requests.get(url, params={"category": "linear", "symbol": symbol}, timeout=5)
            list_items = resp.json().get("result", {}).get("list", [])
            if list_items:
                return float(list_items[0].get("lastPrice", 0.0))
        except Exception:
            pass
        return 0.0

    def close_position(self, symbol: str, qty: float, side: str) -> str:
        # Side to close: if current side is LONG (Buy), close side is Sell, and vice-versa
        close_side = "Sell" if side in ["Buy", "LONG"] else "Buy"
        endpoint = f"{self.base_url}/v5/order/create"
        timestamp = str(int(time.time() * 1000))
        payload = {
            "category": "linear",
            "symbol": symbol,
            "side": close_side,
            "orderType": "Market",
            "qty": str(qty),
            "reduceOnly": True,
            "positionIdx": 0
        }
        body_str = json.dumps(payload)
        signature = self._generate_signature(timestamp, body_str)
        headers = self._get_headers(timestamp, signature)
        try:
            resp = requests.post(endpoint, headers=headers, data=body_str, timeout=5)
            return resp.json().get("result", {}).get("orderId", "")
        except Exception as exc:
            raise ExecutionError(f"Failed to close position: {exc}") from exc