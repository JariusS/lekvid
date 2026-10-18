"""Unit tests for the Quantitative Risk Manager.
Tests position sizing, dynamic leverage math, VaR 95%, and margin threshold enforcement.
"""

import numpy as np
import pytest

from models import InsufficientMarginError
from risk_manager import RiskManager


def test_calculate_dynamic_leverage_bounds():
    manager = RiskManager()
    
    # Ultra-tight stop loss (0.1%): should hit maximum ceiling of 15.0x
    lev_tight = manager.calculate_dynamic_leverage(entry_price=65000.0, stop_loss_price=64935.0)
    assert lev_tight == 15.0

    # Very wide stop loss (25%): 1.0 / (0.25 + 0.005) = 3.9x
    lev_wide = manager.calculate_dynamic_leverage(entry_price=65000.0, stop_loss_price=48750.0)
    assert lev_wide == 3.9

    # Extremely wide stop loss (>100% equivalent): hits floor of 1.0x
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