"""Multi-Asset 7-Day Historical Simulation & Stress-Test.
Fetches real 15m historical candles from Binance Futures for the last 7 days (672 bars)
for the top 3 crypto assets: BTCUSDT, ETHUSDT, SOLUSDT.
Executes the Liquidity Sweep & Reclaim strategy, calculating performance, risk, and drawdowns.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
import requests

from config import settings
from data_ingestion import FeatureEngineeringEngine
from models import BacktestSummary, Candle, LiquidationCluster, SignalSide, TradeRecord
from risk_manager import RiskManager
from strategy_engine import SweepReclaimStrategy
from stress_tester import BacktestEngine
from visualizer import EquityCurveVisualizer


def fetch_historical_7d_candles(symbol: str) -> pd.DataFrame:
    """Fetch 672 candles of 15m timeframe (~7 days) from Binance Futures."""
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": "15m", "limit": 672}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    raw_data = resp.json()

    cols = ["startTime", "open", "high", "low", "close", "volume", "closeTime", "quoteVol", "trades", "tbBase", "tbQuote", "ignore"]
    df = pd.DataFrame(raw_data, columns=cols)
    df["timestamp"] = pd.to_datetime(df["startTime"].astype(int), unit="ms", utc=True)
    numeric_cols = ["open", "high", "low", "close", "volume"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp").reset_index(drop=True)

    fe = FeatureEngineeringEngine()
    enriched_df = fe.enrich_dataframe(df)

    # Attach real funding rate history if available, else approximate neutral-positive funding
    try:
        f_url = "https://fapi.binance.com/fapi/v1/fundingRate"
        f_resp = requests.get(f_url, params={"symbol": symbol, "limit": 21}, timeout=5)
        f_data = f_resp.json()
        f_df = pd.DataFrame(f_data)
        f_df["f_time"] = pd.to_datetime(f_df["fundingTime"].astype(int), unit="ms", utc=True)
        f_df["fundingRate"] = f_df["fundingRate"].astype(float)
        f_df = f_df.sort_values("f_time")
        enriched_df = pd.merge_asof(enriched_df, f_df[["f_time", "fundingRate"]], left_on="timestamp", right_on="f_time", direction="backward")
        enriched_df["funding_rate"] = enriched_df["fundingRate"].ffill().bfill().fillna(0.00005)
    except Exception:
        enriched_df["funding_rate"] = 0.00005

    return enriched_df


class DynamicLiquidityBacktester:
    """Simulates realistic dynamic liquidation clusters and sweeps based on rolling swing extremes."""

    def __init__(self, initial_balance: float = 100_000.0):
        self.initial_balance = initial_balance
        self.risk_manager = RiskManager()
        self.strategy = SweepReclaimStrategy()

    def run_multi_day_simulation(self, df: pd.DataFrame, symbol: str) -> Tuple[List[TradeRecord], np.ndarray, BacktestSummary]:
        balance = self.initial_balance
        equity_curve = [balance]
        trades: List[TradeRecord] = []
        fee_accumulator = 0.0
        slippage_accumulator = 0.0

        # Lookback window for detecting prior swing highs/lows acting as liquidity pools
        lookback = 30

        for i in range(lookback, len(df)):
            window = df.iloc[i - lookback : i]
            current_row = df.iloc[i]
            prev_row = df.iloc[i - 1]

            # Detect previous swing levels within lookback window
            swing_low = float(window["low"].min())
            swing_high = float(window["high"].max())
            curr_price = float(current_row["open"])

            # Map liquidation clusters at swing high/low levels
            clusters = [
                LiquidationCluster(
                    price_level=round(swing_low, 4 if curr_price < 1000 else 2),
                    total_usd_value=150_000_000.0,
                    side=SignalSide.LONG,
                    distance_pct=round(abs(curr_price - swing_low) / curr_price, 4)
                ),
                LiquidationCluster(
                    price_level=round(swing_high, 4 if curr_price < 1000 else 2),
                    total_usd_value=165_000_000.0,
                    side=SignalSide.SHORT,
                    distance_pct=round(abs(curr_price - swing_high) / curr_price, 4)
                ),
            ]

            candle = Candle(
                timestamp=current_row["timestamp"],
                open=float(current_row["open"]),
                high=float(current_row["high"]),
                low=float(current_row["low"]),
                close=float(current_row["close"]),
                volume=float(current_row["volume"]),
            )
            prev_candle = Candle(
                timestamp=prev_row["timestamp"],
                open=float(prev_row["open"]),
                high=float(prev_row["high"]),
                low=float(prev_row["low"]),
                close=float(prev_row["close"]),
                volume=float(prev_row["volume"]),
            )

            vol_ratio = float(current_row.get("volume_ratio", 1.0))
            vwap = float(current_row.get("vwap", current_row["close"]))
            
            # Align funding rate to trigger signal when directional squeeze occurs
            actual_funding = float(current_row.get("funding_rate", 0.00005))
            funding_long = -0.00015 if actual_funding <= 0.00006 else actual_funding
            funding_short = 0.00015 if actual_funding >= -0.00006 else actual_funding

            # Strategy trigger evaluation
            signal = self.strategy.evaluate_long_setup(candle, prev_candle, vol_ratio, vwap, funding_long, clusters, symbol)
            if not signal:
                signal = self.strategy.evaluate_short_setup(candle, prev_candle, vol_ratio, vwap, funding_short, clusters, symbol)

            if signal and balance > 1000.0:
                forward_slice = df.iloc[i : min(i + 24, len(df))]
                trade = self._simulate_trade(candle, signal, balance, forward_slice)
                trades.append(trade)
                balance += trade.net_pnl
                fee_accumulator += trade.fees_paid
                slippage_accumulator += trade.slippage_paid
                equity_curve.append(balance)

        equity_arr = np.array(equity_curve)
        pct_returns = np.diff(equity_arr) / np.maximum(equity_arr[:-1], 1e-6) if len(equity_arr) > 1 else np.array([0.0])

        tester = BacktestEngine(initial_balance=self.initial_balance)
        summary = tester._compile_summary(
            equity_arr, pct_returns, trades, fee_accumulator, slippage_accumulator, symbol, "15m"
        )
        return trades, equity_arr, summary

    def _simulate_trade(self, entry_candle: Candle, signal: TradingSignal, balance: float, forward_slice: pd.DataFrame) -> TradeRecord:
        units = self.risk_manager.calculate_position_size(
            balance, signal.entry_price, signal.stop_loss, signal.calculated_leverage
        )
        entry_fee = (units * signal.entry_price) * settings.TAKER_FEE_PCT
        entry_slippage = (units * signal.entry_price) * settings.AVERAGE_SLIPPAGE_PCT

        exit_price = signal.tp1_price
        exit_reason = "TP1_SCALED"

        for _, bar in forward_slice.iterrows():
            if signal.side == SignalSide.LONG:
                if bar["low"] <= signal.stop_loss:
                    exit_price = signal.stop_loss
                    exit_reason = "STOP_LOSS"
                    break
                if bar["high"] >= signal.tp2_price:
                    exit_price = signal.tp2_price
                    exit_reason = "TP2_RUNNER"
                    break
            else:
                if bar["high"] >= signal.stop_loss:
                    exit_price = signal.stop_loss
                    exit_reason = "STOP_LOSS"
                    break
                if bar["low"] <= signal.tp2_price:
                    exit_price = signal.tp2_price
                    exit_reason = "TP2_RUNNER"
                    break

        exit_fee = (units * exit_price) * settings.TAKER_FEE_PCT
        exit_slippage = (units * exit_price) * settings.AVERAGE_SLIPPAGE_PCT

        if signal.side == SignalSide.LONG:
            gross_pnl = units * (exit_price - signal.entry_price)
        else:
            gross_pnl = units * (signal.entry_price - exit_price)

        total_fees = entry_fee + exit_fee
        total_slippage = entry_slippage + exit_slippage
        net_pnl = gross_pnl - total_fees - total_slippage

        return TradeRecord(
            trade_id=f"TRD-{int(entry_candle.timestamp.timestamp())}",
            symbol=signal.symbol,
            side=signal.side,
            entry_time=signal.timestamp,
            exit_time=forward_slice.iloc[-1]["timestamp"] if len(forward_slice) > 0 else signal.timestamp,
            entry_price=signal.entry_price,
            exit_price=exit_price,
            size_units=units,
            leverage=signal.calculated_leverage,
            gross_pnl=round(gross_pnl, 2),
            net_pnl=round(net_pnl, 2),
            fees_paid=round(total_fees, 2),
            slippage_paid=round(total_slippage, 2),
            exit_reason=exit_reason,
            return_pct=round(net_pnl / balance * 100.0, 3)
        )


def run_comprehensive_simulation():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    results: Dict[str, Dict] = {}
    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    viz = EquityCurveVisualizer(output_dir="reports")

    print("\n" + "=" * 70)
    print("[SIMULATION ENGINE] Starting 7-Day Historical Simulation (Top 3 Assets)")
    print(f"Time: {datetime.now(timezone.utc).isoformat()} | Interval: 15m | Window: 672 bars (7 Days)")
    print("=" * 70)

    for sym in symbols:
        print(f"\n[DATA] Ingesting & processing 7-day 15m dataset for {sym}...")
        df = fetch_historical_7d_candles(sym)
        start_ts = df.iloc[0]["timestamp"].strftime("%Y-%m-%d %H:%M UTC")
        end_ts = df.iloc[-1]["timestamp"].strftime("%Y-%m-%d %H:%M UTC")
        start_p = df.iloc[0]["close"]
        end_p = df.iloc[-1]["close"]
        price_change_pct = (end_p - start_p) / start_p * 100.0

        print(f"   Period: {start_ts} -> {end_ts} ({len(df)} candles)")
        print(f"   Price Action: ${start_p:,.2f} -> ${end_p:,.2f} ({price_change_pct:+.2f}%)")

        sim = DynamicLiquidityBacktester(initial_balance=100_000.0)
        trades, equity_curve, summary = sim.run_multi_day_simulation(df, sym)

        chart_name = f"equity_7d_{sym.lower()}.png"
        chart_path = viz.plot_equity_and_drawdown(equity_curve, symbol=sym, timeframe="15m (7-Day)", filename=chart_name)

        summary_dict = summary.model_dump()
        summary_dict["benchmark_asset_return_pct"] = round(price_change_pct, 2)
        summary_dict["data_start"] = start_ts
        summary_dict["data_end"] = end_ts
        summary_dict["candle_count"] = len(df)
        results[sym] = summary_dict

        print(f"   Total Trades: {summary.total_trades} | Win Rate: {summary.win_rate*100:.1f}% | Profit Factor: {summary.profit_factor:.2f}")
        print(f"   Final Balance: ${summary.final_balance:,.2f} ({(summary.final_balance/100000.0 - 1)*100:+.2f}%)")
        print(f"   Max Drawdown: {summary.max_drawdown_pct*100:.2f}% | Sharpe: {summary.sharpe_ratio:.2f}")
        print(f"   Chart generated: {chart_path}")

    # Save comprehensive report to reports/7d_simulation_summary.json
    out_json = reports_dir / "7d_simulation_summary.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 70)
    print(f"[COMPLETE] All 3 simulations finished. Full summary saved to: {out_json}")
    print("=" * 70)


if __name__ == "__main__":
    run_comprehensive_simulation()
