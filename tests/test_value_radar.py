# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.value_radar import (
    _passes_quality_gates,
    _fair_price_reasons,
    build_value_radar_section,
    scan_watchlist,
)

GREAT_COMPANY = {
    "roe": 25,
    "gross_margin": 50,
    "operating_margin": None,
    "revenue_growth": 12,
    "debt_to_equity": 40,
    "free_cash_flow": 1_000_000,
    "current_price": 100,
    "high_52w": 130,
    "peg_ratio": 1.0,
    "pe_ratio": 20,
}


def test_passes_quality_gates_true_for_great_company():
    assert _passes_quality_gates(GREAT_COMPANY) is True


def test_fails_quality_gates_when_roe_too_low():
    weak = dict(GREAT_COMPANY, roe=5)
    assert _passes_quality_gates(weak) is False


def test_fails_quality_gates_when_debt_too_high():
    weak = dict(GREAT_COMPANY, debt_to_equity=150)
    assert _passes_quality_gates(weak) is False


def test_fails_quality_gates_when_fcf_negative():
    weak = dict(GREAT_COMPANY, free_cash_flow=-500)
    assert _passes_quality_gates(weak) is False


def test_fair_price_reasons_detects_discount_from_high():
    reasons = _fair_price_reasons(GREAT_COMPANY)
    assert any("52w" in r for r in reasons)
    assert any("PEG" in r for r in reasons)


def test_fair_price_reasons_empty_when_expensive():
    expensive = dict(GREAT_COMPANY, current_price=129, peg_ratio=3.0, pe_ratio=40)
    assert _fair_price_reasons(expensive) == []


def test_scan_watchlist_includes_only_quality_and_fair_price_hits():
    fundamentals_by_ticker = {
        "GOOD": GREAT_COMPANY,
        "EXPENSIVE": dict(GREAT_COMPANY, current_price=129, peg_ratio=3.0, pe_ratio=40),
        "WEAK": dict(GREAT_COMPANY, roe=5),
    }

    def fake_fetch(ticker):
        return fundamentals_by_ticker.get(ticker, {})

    hits = scan_watchlist(["GOOD", "EXPENSIVE", "WEAK"], fetch_fundamentals=fake_fetch)
    tickers = [h[0] for h in hits]
    assert tickers == ["GOOD"]


def test_build_value_radar_section_empty_when_no_hits():
    section = build_value_radar_section(
        watchlist_tickers=["WEAK"],
        fmp_api_key="",
        fetch_fundamentals=lambda ticker: dict(GREAT_COMPANY, roe=5),
    )
    assert section == ""


def test_build_value_radar_section_formats_hit():
    section = build_value_radar_section(
        watchlist_tickers=["GOOD"],
        fmp_api_key="",
        fetch_fundamentals=lambda ticker: GREAT_COMPANY,
    )
    assert "GOOD" in section
    assert section.startswith("•")


def test_build_value_radar_section_trims_to_max_chars():
    tickers = [f"T{i}" for i in range(10)]
    section = build_value_radar_section(
        watchlist_tickers=tickers,
        fmp_api_key="",
        max_chars=50,
        fetch_fundamentals=lambda ticker: GREAT_COMPANY,
    )
    assert len(section) <= 50
