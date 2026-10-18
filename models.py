"""Domain models, custom exceptions, and structured schemas for the quantitative system.
Complies with Uncle Bob's Clean Architecture and strict Pydantic v2 validation.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# --- DOMAIN EXCEPTIONS ---
class TradingBotException(Exception):
    """Base exception for all trading bot domain errors."""


class InsufficientMarginError(TradingBotException):
    """Raised when available collateral is inadequate for calculated position sizing."""


class ClusterNotFoundError(TradingBotException):
    """Raised when no qualifying liquidation cluster is detected within criteria."""


class OverfittingDetectedError(TradingBotException):
    """Raised when CSCV yields an unacceptably high Probability of Backtest Overfitting (PBO)."""


class TestingFailedError(TradingBotException):
    """Raised when mandatory pre-flight pytest suite fails before backtesting/execution."""


class DataIngestionError(TradingBotException):
    """Raised when market data ingestion or timestamp alignment fails."""


class ExecutionError(TradingBotException):
    """Raised when order transmission or fill confirmation fails on exchange API."""


# --- ENUMS ---
class SignalSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class MarketRegime(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"
    FLASH_CRASH = "FLASH_CRASH"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


# --- VALUE OBJECTS & SCHEMAS ---
class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def range(self) -> float:
        return self.high - self.low


class LiquidationCluster(BaseModel):
    price_level: float
    total_usd_value: float
    side: SignalSide
    distance_pct: float
    open_interest_delta: float = 0.0


class TradingSignal(BaseModel):
    symbol: str
    timestamp: datetime
    side: SignalSide
    entry_price: float
    stop_loss: float
    tp1_price: float
    tp2_price: float
    trailing_callback_pct: float
    calculated_leverage: float
    cluster_price_swept: float
    volume_ratio: float
    funding_rate: float
    rationale: str


class TradeRecord(BaseModel):
    trade_id: str
    symbol: str
    side: SignalSide
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    size_units: float
    leverage: float
    gross_pnl: float
    net_pnl: float
    fees_paid: float
    slippage_paid: float
    exit_reason: str
    return_pct: float


class BacktestSummary(BaseModel):
    timestamp: str = Field(description="ISO 8601 generation timestamp")
    symbol: str
    timeframe: str
    initial_balance: float
    final_balance: float
    total_trades: int
    win_rate: float
    profit_factor: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    var_95: float
    expected_shortfall: float
    pbo_score: float
    execution_fee_cost: float
    slippage_cost: float
    unit_tests_passed: bool