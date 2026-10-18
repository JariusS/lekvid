# Google Antigravity Agent Project Guide: Liquidity Sweep & Reclaim

## Project Overview
This repository contains a production-grade algorithmic trading system tailored for the Bybit V5 Perpetual Futures API, implementing the Liquidity Sweep & Reclaim strategy. It is built specifically for autonomous execution, walk-forward testing, synthetic stress-testing, and risk governance by the Google Antigravity Agent.

---

## 1. Directory Structure

- .gemini/rules                 # Antigravity agent operational directives & MCP configuration
- gemini.md                     # Antigravity project guide
- config.py                     # Pydantic Settings & environment validation
- models.py                     # Pydantic data schemas, signals, trade orders, and summary schema
- data_ingestion.py             # Data parsers (Bybit V5, Binance, CoinGecko), GARCH, Alpha101
- strategy_engine.py            # Pure domain logic for Liquidity Sweep & Reclaim
- risk_manager.py               # Dynamic leverage calculation, VaR 95%, Expected Shortfall
- market_simulator.py           # Dual-Mode Simulator (Replay + Synthetic Generative Engine)
- stress_tester.py              # Walk-Forward validation, CSCV combinatorial matrix, PBO score
- execution_engine.py           # Decoupled execution classes (LiveExecutionEngine vs SimulatedExecutionEngine)
- visualizer.py                 # Matplotlib dual-panel equity curve & drawdown exporter
- notifier.py                   # Async Telegram alerting with chart upload and JSON reporting
- tests/test_strategy.py        # Pytest validation for Sweep & Reclaim triggers & filters
- tests/test_risk.py            # Pytest validation for leverage, margin, and VaR math
- main.py                       # Unified CLI entry point for Backtest, Generate, and Live modes
- requirements.txt              # Production and testing Python dependencies
- README.md                     # Architecture overview & setup instructions

---

## 2. Antigravity Agent Execution Protocol

When invoked by Google Antigravity, the agent follows this sequence:
1. Pre-flight Gate: Execute pytest tests/ -v. Halt on failure with TestingFailedError.
2. Data Pipeline & Feature Extraction: Ingest OHLCV, align UTC, compute Log Returns, GARCH(1,1), Alpha101.
3. Signal Generation: Screen $100M+ clusters, check wick sweep, volume > 1.8x SMA20, close reclaim.
4. Risk Allocation: Dynamic leverage min(15x, 1 / (SL_dist + Margin)), scale-out TP1 at VWAP, TP2 at opposing cluster, runner with 0.6% callback.
5. Evaluation & Artifact Export: Walk-Forward, CSCV PBO score, render reports/equity_curve.png, export reports/backtest_summary.json.