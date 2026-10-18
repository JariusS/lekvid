"""Visualizer: Matplotlib dual-panel equity curve and drawdown chart generator.
Saves high-resolution visual artifact to reports/equity_curve.png for Antigravity agent introspection.
"""

import os
from pathlib import Path
from typing import List, Optional
import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


class EquityCurveVisualizer:
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_equity_and_drawdown(
        self,
        equity_series: np.ndarray,
        symbol: str = "BTCUSDT",
        timeframe: str = "15m",
        filename: str = "equity_curve.png"
    ) -> str:
        output_path = self.output_dir / filename
        if not HAS_MATPLOTLIB or len(equity_series) == 0:
            with open(output_path, "wb") as f:
                f.write(b"")
            return str(output_path)

        peaks = np.maximum.accumulate(equity_series)
        drawdowns = (equity_series - peaks) / np.maximum(peaks, 1e-6) * 100.0

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(12, 8), sharex=True,
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor="#0B0F19"
        )

        ax1.set_facecolor("#111827")
        ax1.plot(equity_series, color="#06B6D4", linewidth=2.0, label="Portfolio Equity ($)")
        ax1.axhline(equity_series[0], color="#9CA3AF", linestyle="--", alpha=0.5, label="Initial Capital")
        ax1.set_title(f"Quantitative Backtest Performance - {symbol} [{timeframe}]", color="#F9FAFB", fontsize=14, pad=12)
        ax1.set_ylabel("Account Balance ($USD)", color="#E5E7EB", fontsize=11)
        ax1.grid(True, color="#1F2937", linestyle=":", alpha=0.6)
        ax1.tick_params(colors="#9CA3AF")
        ax1.legend(loc="upper left", facecolor="#1F2937", edgecolor="#374151", labelcolor="#F9FAFB")

        ax2.set_facecolor("#111827")
        ax2.fill_between(range(len(drawdowns)), drawdowns, 0, color="#EF4444", alpha=0.4, label="Drawdown (%)")
        ax2.plot(drawdowns, color="#DC2626", linewidth=1.2)
        ax2.set_ylabel("Drawdown %", color="#E5E7EB", fontsize=11)
        ax2.set_xlabel("Trade / Bar Progression", color="#E5E7EB", fontsize=11)
        ax2.grid(True, color="#1F2937", linestyle=":", alpha=0.6)
        ax2.tick_params(colors="#9CA3AF")
        ax2.legend(loc="lower left", facecolor="#1F2937", edgecolor="#374151", labelcolor="#F9FAFB")

        plt.tight_layout()
        plt.savefig(output_path, dpi=180, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)

        return str(output_path)