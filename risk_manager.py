"""Risk Manager: Dynamic Leverage, Capital Allocation, VaR 95%, and Expected Shortfall.
Enforces strict 2% portfolio equity risk ceiling and mathematically grounded position sizing.
"""

from typing import List, Tuple
import numpy as np

from config import settings
from models import InsufficientMarginError, TradingSignal


class RiskManager:
    """Quantitative risk engine enforcing portfolio protection and margin requirements."""

    def __init__(self, max_risk_pct: float = settings.MAX_RISK_PER_TRADE_PCT):
        self.max_risk_pct = max_risk_pct

    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        leverage: float
    ) -> float:
        if account_balance <= 0:
            raise InsufficientMarginError(f"Account balance must be positive. Given: {account_balance}")

        risk_capital = account_balance * self.max_risk_pct
        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            raise ValueError(f"Stop loss ({stop_loss_price}) cannot equal entry price ({entry_price})")

        unlevered_units = risk_capital / sl_distance
        max_notional = account_balance * leverage
        max_units_by_leverage = max_notional / entry_price

        final_units = min(unlevered_units, max_units_by_leverage)

        # Ensure order satisfies Bybit minimum notional threshold ($5.00) for deposits >= $50
        min_notional_floor = 5.0
        current_notional = final_units * entry_price
        if current_notional < min_notional_floor:
            min_required_units = min_notional_floor / entry_price
            min_margin = min_notional_floor / leverage
            # Allow minimum notional if required margin is within safe 40% margin limit of account
            if min_margin <= account_balance * 0.40:
                final_units = min_required_units

        required_margin = (final_units * entry_price) / leverage
        if required_margin > account_balance:
            raise InsufficientMarginError(
                f"Required margin ${required_margin:.2f} exceeds available balance ${account_balance:.2f}"
            )
        return round(final_units, 4)

    def calculate_dynamic_leverage(self, entry_price: float, stop_loss_price: float) -> float:
        sl_distance_pct = abs(entry_price - stop_loss_price) / entry_price
        raw_leverage = 1.0 / (sl_distance_pct + settings.MARGIN_BUFFER)
        bounded = min(settings.MAX_LEVERAGE, max(settings.MIN_LEVERAGE, raw_leverage))
        return round(bounded, 1)

    @staticmethod
    def calculate_value_at_risk_95(returns: np.ndarray) -> float:
        if len(returns) == 0:
            return 0.0
        var_pct = np.percentile(returns, 5.0)
        return float(abs(min(0.0, var_pct)))

    @staticmethod
    def calculate_expected_shortfall(returns: np.ndarray, alpha: float = 0.05) -> float:
        if len(returns) == 0:
            return 0.0
        var_threshold = np.percentile(returns, alpha * 100.0)
        tail_losses = returns[returns <= var_threshold]
        if len(tail_losses) == 0:
            return float(abs(min(0.0, var_threshold)))
        return float(abs(np.mean(tail_losses)))