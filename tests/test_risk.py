"""Unit tests for the Quantitative Risk Manager.
Tests position sizing, dynamic leverage math, VaR 95%, and margin threshold enforcement.
"""

import numpy as np
import pytest

from models import InsufficientMarginError
from risk_manager import RiskManager


def test_calculate_dynamic_leverage_bounds():
    manager = RiskManager()
    
    # Ultra-tight stop loss (0.1%): must strictly remain 1.0x
    lev_tight = manager.calculate_dynamic_leverage(entry_price=65000.0, stop_loss_price=64935.0)
    assert lev_tight == 1.0

    # Very wide stop loss (25%): must strictly remain 1.0x
    lev_wide = manager.calculate_dynamic_leverage(entry_price=65000.0, stop_loss_price=48750.0)
    assert lev_wide == 1.0

    # Extremely wide stop loss (>100% equivalent): must strictly remain 1.0x
    lev_floor = manager.calculate_dynamic_leverage(entry_price=65000.0, stop_loss_price=0.0)
    assert lev_floor == 1.0


def test_position_sizing_respects_two_percent_risk():
    manager = RiskManager(max_risk_pct=0.02)
    account_balance = 50_000.0
    entry_price = 60_000.0
    stop_loss = 58_800.0
    leverage = 5.0

    units = manager.calculate_position_size(
        account_balance=account_balance,
        entry_price=entry_price,
        stop_loss_price=stop_loss,
        leverage=leverage
    )

    dollar_risk = units * abs(entry_price - stop_loss)
    allowed_risk = account_balance * 0.02
    assert dollar_risk <= allowed_risk + 0.01


def test_position_sizing_raises_insufficient_margin():
    manager = RiskManager()
    with pytest.raises(InsufficientMarginError):
        manager.calculate_position_size(
            account_balance=0.0,
            entry_price=60_000.0,
            stop_loss_price=59_000.0,
            leverage=5.0
        )


def test_var_and_expected_shortfall():
    np.random.seed(42)
    returns = np.random.normal(loc=0.001, scale=0.02, size=1000)

    var_95 = RiskManager.calculate_value_at_risk_95(returns)
    es = RiskManager.calculate_expected_shortfall(returns, alpha=0.05)

    assert var_95 > 0.0
    assert es >= var_95


def test_small_deposit_fifty_dollars():
    manager = RiskManager(max_risk_pct=0.02)
    deposit = 50.0  # Micro account starting from $50
    entry_price = 150.0  # e.g. SOLUSDT
    stop_loss = 147.0    # 2% stop loss
    leverage = 5.0

    units = manager.calculate_position_size(
        account_balance=deposit,
        entry_price=entry_price,
        stop_loss_price=stop_loss,
        leverage=leverage
    )

    notional = units * entry_price
    required_margin = notional / leverage

    # Must satisfy Bybit $5 minimum notional
    assert notional >= 5.0
    # Margin must not exceed account balance ($50)
    assert required_margin <= deposit