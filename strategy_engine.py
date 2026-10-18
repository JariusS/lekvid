"""Subsystem E: Pure Domain Trading Strategy Engine.
Implements the 'Liquidity Sweep & Reclaim' strategy for Perpetual Futures.
Completely decoupled from network I/O, persistence, and exchange APIs.
Strict adherence to CQS and Martin's Clean Code principles.
"""

from datetime import datetime
from typing import List, Optional
import pandas as pd

from config import settings
from models import Candle, LiquidationCluster, SignalSide, TradingSignal


class LiquidityClusterDetector:
    """Detects institutional liquidation pools based on depth and open interest distribution."""

    def filter_qualifying_clusters(
        self,
        clusters: List[LiquidationCluster],
        current_price: float,
        target_side: SignalSide
    ) -> List[LiquidationCluster]:
        qualifying: List[LiquidationCluster] = []
        for cluster in clusters:
            if cluster.side != target_side:
                continue
            if cluster.total_usd_value < settings.MIN_CLUSTER_USD_VALUE:
                continue
            dist_pct = abs(cluster.price_level - current_price) / current_price
            if settings.CLUSTER_MIN_DIST_PCT <= dist_pct <= settings.CLUSTER_MAX_DIST_PCT:
                qualifying.append(cluster)
        return qualifying

    def select_nearest_cluster(self, qualifying_clusters: List[LiquidationCluster], current_price: float) -> Optional[LiquidationCluster]:
        if not qualifying_clusters:
            return None
        return min(qualifying_clusters, key=lambda c: abs(c.price_level - current_price))


class SweepReclaimStrategy:
    """Evaluates market state to produce actionable Sweep & Reclaim signals."""

    def __init__(self, cluster_detector: Optional[LiquidityClusterDetector] = None):
        self.detector = cluster_detector or LiquidityClusterDetector()

    def evaluate_long_setup(
        self,
        candle: Candle,
        previous_candle: Candle,
        volume_ratio: float,
        vwap_price: float,
        funding_rate: float,
        clusters: List[LiquidationCluster],
        symbol: str
    ) -> Optional[TradingSignal]:
        if funding_rate > settings.FUNDING_RATE_LONG_THRESHOLD:
            return None

        qualifying = self.detector.filter_qualifying_clusters(clusters, candle.open, SignalSide.LONG)
        target_cluster = self.detector.select_nearest_cluster(qualifying, candle.open)
        if not target_cluster:
            return None

        support_level = target_cluster.price_level
        is_sweep = candle.low < support_level
        is_reclaim = candle.close > support_level
        is_volume_spike = volume_ratio >= settings.VOLUME_EXPANSION_FACTOR

        if not (is_sweep and is_reclaim and is_volume_spike):
            return None

        return self._build_long_signal(candle, target_cluster, vwap_price, volume_ratio, funding_rate, symbol)

    def _build_long_signal(
        self,
        candle: Candle,
        cluster: LiquidationCluster,
        vwap_price: float,
        volume_ratio: float,
        funding_rate: float,
        symbol: str
    ) -> TradingSignal:
        stop_loss = candle.low * (1.0 - settings.STOP_LOSS_BUFFER_PCT)
        sl_distance_pct = max((candle.close - stop_loss) / candle.close, 0.005)
        calculated_leverage = 1.0
        tp1_price = max(vwap_price, candle.close * 1.01)
        tp2_price = candle.close * (1.0 + (sl_distance_pct * 3.0))

        return TradingSignal(
            symbol=symbol,
            timestamp=candle.timestamp,
            side=SignalSide.LONG,
            entry_price=candle.close,
            stop_loss=round(stop_loss, 2),
            tp1_price=round(tp1_price, 2),
            tp2_price=round(tp2_price, 2),
            trailing_callback_pct=settings.TRAILING_STOP_CALLBACK_PCT,
            calculated_leverage=calculated_leverage,
            cluster_price_swept=cluster.price_level,
            volume_ratio=round(volume_ratio, 2),
            funding_rate=funding_rate,
            rationale=f"Long Liquidity Sweep of ${cluster.total_usd_value/1e6:.1f}M cluster at {cluster.price_level} with volume {volume_ratio:.2f}x SMA20"
        )

    def evaluate_short_setup(
        self,
        candle: Candle,
        previous_candle: Candle,
        volume_ratio: float,
        vwap_price: float,
        funding_rate: float,
        clusters: List[LiquidationCluster],
        symbol: str
    ) -> Optional[TradingSignal]:
        if funding_rate < settings.FUNDING_RATE_SHORT_THRESHOLD:
            return None

        qualifying = self.detector.filter_qualifying_clusters(clusters, candle.open, SignalSide.SHORT)
        target_cluster = self.detector.select_nearest_cluster(qualifying, candle.open)
        if not target_cluster:
            return None

        resistance_level = target_cluster.price_level
        is_sweep = candle.high > resistance_level
        is_reclaim = candle.close < resistance_level
        is_volume_spike = volume_ratio >= settings.VOLUME_EXPANSION_FACTOR

        if not (is_sweep and is_reclaim and is_volume_spike):
            return None

        return self._build_short_signal(candle, target_cluster, vwap_price, volume_ratio, funding_rate, symbol)

    def _build_short_signal(
        self,
        candle: Candle,
        cluster: LiquidationCluster,
        vwap_price: float,
        volume_ratio: float,
        funding_rate: float,
        symbol: str
    ) -> TradingSignal:
        stop_loss = candle.high * (1.0 + settings.STOP_LOSS_BUFFER_PCT)
        sl_distance_pct = max((stop_loss - candle.close) / candle.close, 0.005)
        calculated_leverage = 1.0
        tp1_price = min(vwap_price, candle.close * 0.99)
        tp2_price = candle.close * (1.0 - (sl_distance_pct * 3.0))

        return TradingSignal(
            symbol=symbol,
            timestamp=candle.timestamp,
            side=SignalSide.SHORT,
            entry_price=candle.close,
            stop_loss=round(stop_loss, 2),
            tp1_price=round(tp1_price, 2),
            tp2_price=round(tp2_price, 2),
            trailing_callback_pct=settings.TRAILING_STOP_CALLBACK_PCT,
            calculated_leverage=calculated_leverage,
            cluster_price_swept=cluster.price_level,
            volume_ratio=round(volume_ratio, 2),
            funding_rate=funding_rate,
            rationale=f"Short Liquidity Sweep of ${cluster.total_usd_value/1e6:.1f}M cluster at {cluster.price_level} with volume {volume_ratio:.2f}x SMA20"
        )