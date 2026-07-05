# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.portfolio.moomoo_reader import _build_row


def test_build_row_strips_market_prefix_and_uppercases():
    row = _build_row(
        code="US.AAPL",
        qty=10,
        cost_price=150.0,
        nominal_price=200.0,
        market_val=2000.0,
        pl_val=500.0,
    )

    assert row == {
        "ticker": "AAPL",
        "shares": 10,
        "avg_buy_price": 150.0,
        "current_price": 200.0,
        "total_value": 2000.0,
        "pnl": 500.0,
    }


def test_build_row_handles_code_without_prefix():
    row = _build_row(
        code="aapl",
        qty=5,
        cost_price=100.0,
        nominal_price=110.0,
        market_val=550.0,
        pl_val=50.0,
    )

    assert row["ticker"] == "AAPL"


def test_get_positions_returns_empty_when_moomoo_api_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "moomoo":
            raise ImportError("moomoo-api not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from src.portfolio.moomoo_reader import MoomooPortfolioReader

    reader = MoomooPortfolioReader()
    assert reader.get_positions() == {}
