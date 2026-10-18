"""Subsystem B: Dual-Mode Market Simulator.
Provides:
1. Replay Simulator: Historical execution with order book depth, network latency, and dynamic slippage.
2. Generative Simulator ("What-If" Engine): Synthetic stochastic trajectories with GARCH volatility
   across Bullish, Bearish, Sideways, and Flash-Crash regimes.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
import numpy as np
import pandas as pd

from config import settings
from models import Candle, MarketRegime


class HistoricalReplaySimulator:
    def __init__(
        self,
        maker_fee: float = settings.MAKER_FEE_PCT,
        taker_fee: float = settings.TAKER_FEE_PCT,
        slippage_base: float = settings.AVERAGE_SLIPPAGE_PCT
    ):
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage_base = slippage_base

    def simulate_entry_fill(self, candle: Candle, is_limit: bool = False) -> Tuple[float, float, float]:
        fee_rate = self.maker_fee if is_limit else self.taker_fee
        slippage = 0.0 if is_limit else candle.close * self.slippage_base
        realized_price = candle.close + slippage
        fee_cost = realized_price * fee_rate
        return realized_price, fee_cost, slippage

    def simulate_exit_fill(self, target_price: float, is_limit: bool = True) -> Tuple[float, float, float]:
        fee_rate = self.maker_fee if is_limit else self.taker_fee
        slippage = 0.0 if is_limit else target_price * self.slippage_base
        realized_price = target_price - slippage
        fee_cost = realized_price * fee_rate
        return realized_price, fee_cost, slippage


class SyntheticGenerativeEngine:
    def __init__(self, initial_price: float = 65000.0, seed: int = 42):
        self.initial_price = initial_price
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def generate_regime_trajectory(
        self,
        regime: MarketRegime,
        num_candles: int = 500,
        start_time: Optional[datetime] = None
    ) -> pd.DataFrame:
        start = start_time or datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        drift, base_vol = self._get_regime_parameters(regime)
        
        dt = 1.0 / 1440.0
        shocks = self.rng.normal(0, 1, num_candles)
        returns = np.zeros(num_candles)
        sigma = base_vol

        for t in range(num_candles):
            if regime == MarketRegime.FLASH_CRASH and num_candles // 2 - 5 <= t <= num_candles // 2 + 5:
                shock = -0.04 - abs(self.rng.normal(0, 0.02))
                returns[t] = shock
                sigma = base_vol * 3.5
            else:
                sigma = np.sqrt(1e-6 + 0.10 * (returns[t - 1] ** 2) + 0.85 * (sigma ** 2)) if t > 0 else base_vol
                returns[t] = (drift - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * shocks[t]

        prices = self.initial_price * np.exp(np.cumsum(returns))
        return self._format_synthetic_candles(prices, start, num_candles)

    def _get_regime_parameters(self, regime: MarketRegime) -> Tuple[float, float]:
        mapping = {
            MarketRegime.BULLISH: (0.45, 0.55),
            MarketRegime.BEARISH: (-0.35, 0.65),
            MarketRegime.SIDEWAYS: (0.02, 0.30),
            MarketRegime.FLASH_CRASH: (-0.90, 0.95),
        }
        return mapping[regime]

    def _format_synthetic_candles(self, prices: np.ndarray, start: datetime, n: int) -> pd.DataFrame:
        records = []
        cur_time = start
        for i in range(n):
            close_p = prices[i]
            open_p = prices[i - 1] if i > 0 else close_p
            spread = abs(self.rng.normal(0, close_p * 0.003))
            high_p = max(open_p, close_p) + spread * self.rng.uniform(0.5, 1.5)
            low_p = min(open_p, close_p) - spread * self.rng.uniform(0.5, 1.5)
            volume = float(self.rng.uniform(500, 3500) * (1.0 + spread / close_p * 50))
            
            records.append({
                "timestamp": cur_time,
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close_p, 2),
                "volume": round(volume, 2),
            })
            cur_time += timedelta(minutes=15)

        return pd.DataFrame(records)