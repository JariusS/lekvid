"""Unit tests for the Liquidity Sweep & Reclaim Strategy Engine.
Enforces Martin's F.I.R.S.T. unit test standards (Fast, Independent, Repeatable, Self-Validating, Timely).
"""

from datetime import datetime, timezone
import pytest

from models import Candle, LiquidationCluster, SignalSide
from strategy_engine import LiquidityClusterDetector, SweepReclaimStrategy


@pytest.fixture
def base_timestamp() -> datetime:
    return datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def qualifying_long_cluster() -> LiquidationCluster:
    return LiquidationCluster(
        price_level=64000.0,
        total_usd_value=120_000_000.0,
        side=SignalSide.LONG,
        distance_pct=0.015
    )


@pytest.fixture
def qualifying_short_cluster() -> LiquidationCluster:
    return LiquidationCluster(
        price_level=66000.0,
        total_usd_value=150_000_000.0,
        side=SignalSide.SHORT,
        distance_pct=0.015
    )


def test_cluster_filter_ignores_under_100m():
    detector = LiquidityClusterDetector()
    clusters = [
        LiquidationCluster(price_level=64000.0, total_usd_value=50_000_000.0, side=SignalSide.LONG, distance_pct=0.015),
        LiquidationCluster(price_level=64100.0, total_usd_value=110_000_000.0, side=SignalSide.LONG, distance_pct=0.015)
    ]
    result = detector.filter_qualifying_clusters(clusters, current_price=65000.0, target_side=SignalSide.LONG)
    assert len(result) == 1
    assert result[0].total_usd_value == 110_000_000.0


def test_cluster_filter_ignores_outside_distance_range():
    detector = LiquidityClusterDetector()
    clusters = [
        LiquidationCluster(price_level=64900.0, total_usd_value=200_000_000.0, side=SignalSide.LONG, distance_pct=0.0015),
        LiquidationCluster(price_level=62000.0, total_usd_value=200_000_000.0, side=SignalSide.LONG, distance_pct=0.046),
        LiquidationCluster(price_level=64000.0, total_usd_value=200_000_000.0, side=SignalSide.LONG, distance_pct=0.015)
    ]
    result = detector.filter_qualifying_clusters(clusters, current_price=65000.0, target_side=SignalSide.LONG)
    assert len(result) == 1
    assert result[0].price_level == 64000.0


def test_long_sweep_trigger_success(base_timestamp, qualifying_long_cluster):
    strategy = SweepReclaimStrategy()
    prev_candle = Candle(timestamp=base_timestamp, open=65000.0, high=65200.0, low=64700.0, close=64800.0, volume=1000.0)
    sweep_candle = Candle(timestamp=base_timestamp, open=64800.0, high=64300.0, low=63850.0, close=64200.0, volume=2500.0)

    signal = strategy.evaluate_long_setup(
        candle=sweep_candle,
        previous_candle=prev_candle,
        volume_ratio=2.2,
        vwap_price=64600.0,
        funding_rate=-0.00025,
        clusters=[qualifying_long_cluster],
        symbol="BTCUSDT"
    )

    assert signal is not None
    assert signal.side == SignalSide.LONG
    assert signal.entry_price == 64200.0
    assert signal.stop_loss < 63850.0
    assert signal.calculated_leverage <= 15.0
    assert signal.tp1_price >= 64600.0


def test_long_sweep_rejects_insufficient_volume(base_timestamp, qualifying_long_cluster):
    strategy = SweepReclaimStrategy()
    candle = Candle(timestamp=base_timestamp, open=64800.0, high=64300.0, low=63850.0, close=64200.0, volume=1200.0)
    prev = Candle(timestamp=base_timestamp, open=65000.0, high=65100.0, low=64700.0, close=64800.0, volume=1000.0)

    signal = strategy.evaluate_long_setup(
        candle=candle,
        previous_candle=prev,
        volume_ratio=1.3,
        vwap_price=64600.0,
        funding_rate=-0.00025,
        clusters=[qualifying_long_cluster],
        symbol="BTCUSDT"
    )
    assert signal is None


def test_short_sweep_trigger_success(base_timestamp, qualifying_short_cluster):
    strategy = SweepReclaimStrategy()
    prev = Candle(timestamp=base_timestamp, open=65000.0, high=65300.0, low=64900.0, close=65200.0, volume=1000.0)
    sweep_candle = Candle(timestamp=base_timestamp, open=65200.0, high=66250.0, low=65700.0, close=65800.0, volume=2800.0)

    signal = strategy.evaluate_short_setup(
        candle=sweep_candle,
        previous_candle=prev,
        volume_ratio=2.1,
        vwap_price=65400.0,
        funding_rate=0.00030,
        clusters=[qualifying_short_cluster],
        symbol="BTCUSDT"
    )

    assert signal is not None
    assert signal.side == SignalSide.SHORT
    assert signal.entry_price == 65800.0
    assert signal.stop_loss > 66250.0
    assert signal.calculated_leverage <= 15.0
    assert signal.tp1_price <= 65400.0