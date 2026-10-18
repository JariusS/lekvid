"""Configuration module using Pydantic Settings for Bybit V5 Quantitative Engine.
Enforces strict type validation, zero hardcoded magic numbers, and secure secret loading.
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Global configuration settings for the algorithmic trading system."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # API Credentials (never hardcode in source)
    BYBIT_API_KEY: str = Field(default="", description="Bybit V5 REST/WS API Key")
    BYBIT_API_SECRET: str = Field(default="", description="Bybit V5 API Secret")
    BYBIT_TESTNET: bool = Field(default=True, description="Whether to connect to Bybit Testnet")
    
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default="", description="Telegram Bot Token for alerts")
    TELEGRAM_CHAT_ID: Optional[str] = Field(default="", description="Telegram Chat ID for alerts")

    # Trading Symbol & Timeframes
    DEFAULT_SYMBOL: str = Field(default="BTCUSDT", description="Primary trading pair")
    TIMEFRAME: str = Field(default="15m", description="Primary timeframe for strategy signals")
    
    # Quantitative Risk Limits
    MAX_RISK_PER_TRADE_PCT: float = Field(default=0.02, description="Max 2% capital risk per trade")
    MAX_LEVERAGE: float = Field(default=15.0, description="Hard cap on dynamic leverage")
    MIN_LEVERAGE: float = Field(default=1.0, description="Minimum leverage floor")
    MARGIN_BUFFER: float = Field(default=0.005, description="Margin buffer for dynamic leverage formula")
    STOP_LOSS_BUFFER_PCT: float = Field(default=0.0025, description="0.25% buffer beyond sweep wick")
    TRAILING_STOP_CALLBACK_PCT: float = Field(default=0.006, description="0.6% trailing callback")

    # Liquidity Sweep Strategy Thresholds
    MIN_CLUSTER_USD_VALUE: float = Field(default=100_000_000.0, description="$100M+ liquidation cluster threshold")
    CLUSTER_MIN_DIST_PCT: float = Field(default=0.005, description="0.5% min distance from spot price")
    CLUSTER_MAX_DIST_PCT: float = Field(default=0.030, description="3.0% max distance from spot price")
    VOLUME_EXPANSION_FACTOR: float = Field(default=1.8, description="Volume must exceed 1.8x SMA20")
    FUNDING_RATE_LONG_THRESHOLD: float = Field(default=-0.0001, description="Funding rate < -0.01% for Long sweep")
    FUNDING_RATE_SHORT_THRESHOLD: float = Field(default=0.0001, description="Funding rate > +0.01% for Short sweep")

    # Take-Profit Scaling Ratios
    TP1_RATIO: float = Field(default=0.50, description="50% position scale-out at VWAP")
    TP2_RATIO: float = Field(default=0.30, description="30% position scale-out at opposing cluster")
    RUNNER_RATIO: float = Field(default=0.20, description="20% trailing runner position")

    # Fee Structure & Realistic Slippage
    MAKER_FEE_PCT: float = Field(default=0.0002, description="0.02% Bybit Maker fee")
    TAKER_FEE_PCT: float = Field(default=0.00055, description="0.055% Bybit Taker fee")
    AVERAGE_SLIPPAGE_PCT: float = Field(default=0.0003, description="0.03% modeled market slippage")
    EXECUTION_LATENCY_MS: int = Field(default=45, description="Simulated order latency in milliseconds")


# Singleton instance
settings = AppConfig()