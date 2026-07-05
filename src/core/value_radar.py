# -*- coding: utf-8 -*-
"""
价值雷达 (Value Radar) — deterministic quality-at-fair-price scanning.

Two passes, both rules-based (no LLM):
1. Watchlist alerts — tickers already in STOCK_LIST/portfolio that currently
   pass "great company" quality gates AND a fair-price trigger.
2. Discovery — large-cap US names outside the watchlist that clear the same
   bars, sourced from FMP's stock screener.

Output is a compact bullet-list Markdown string meant to be appended to the
daily market review message. Returns "" when nothing qualifies.
"""

import logging
import os
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Quality gates ("great company") — overridable via env for tuning.
MIN_ROE = float(os.getenv("VALUE_RADAR_MIN_ROE", "15"))
MIN_MARGIN = float(os.getenv("VALUE_RADAR_MIN_MARGIN", "40"))
MIN_OPERATING_MARGIN = float(os.getenv("VALUE_RADAR_MIN_OPERATING_MARGIN", "20"))
MIN_REVENUE_GROWTH = float(os.getenv("VALUE_RADAR_MIN_REVENUE_GROWTH", "5"))
MAX_DEBT_TO_EQUITY = float(os.getenv("VALUE_RADAR_MAX_DEBT_TO_EQUITY", "100"))

# Fair-price triggers ("fair price") — any one qualifies.
MIN_DISCOUNT_FROM_HIGH_PCT = float(os.getenv("VALUE_RADAR_MIN_DISCOUNT_FROM_HIGH_PCT", "15"))
MAX_PEG = float(os.getenv("VALUE_RADAR_MAX_PEG", "1.5"))
MAX_PE = float(os.getenv("VALUE_RADAR_MAX_PE", "25"))

MAX_WATCHLIST_HITS = 5
MAX_DISCOVERY_HITS = 3
DISCOVERY_SCAN_LIMIT = 20

FetchFundamentals = Callable[[str], Optional[Dict]]


def _passes_quality_gates(f: Dict) -> bool:
    roe = f.get("roe")
    gross_margin = f.get("gross_margin")
    operating_margin = f.get("operating_margin")
    revenue_growth = f.get("revenue_growth")
    debt_to_equity = f.get("debt_to_equity")
    free_cash_flow = f.get("free_cash_flow")

    if roe is None or roe <= MIN_ROE:
        return False
    if not ((gross_margin is not None and gross_margin > MIN_MARGIN)
            or (operating_margin is not None and operating_margin > MIN_OPERATING_MARGIN)):
        return False
    if revenue_growth is None or revenue_growth <= MIN_REVENUE_GROWTH:
        return False
    if debt_to_equity is not None and debt_to_equity >= MAX_DEBT_TO_EQUITY:
        return False
    if free_cash_flow is not None and free_cash_flow <= 0:
        return False
    return True


def _fair_price_reasons(f: Dict) -> List[str]:
    reasons = []
    current_price = f.get("current_price")
    high_52w = f.get("high_52w")
    peg_ratio = f.get("peg_ratio")
    pe_ratio = f.get("pe_ratio")

    if current_price and high_52w and high_52w > 0:
        discount_pct = (high_52w - current_price) / high_52w * 100
        if discount_pct >= MIN_DISCOUNT_FROM_HIGH_PCT:
            reasons.append(f"↓{discount_pct:.0f}% vs 52w高")
    if peg_ratio is not None and 0 < peg_ratio < MAX_PEG:
        reasons.append(f"PEG {peg_ratio:.1f}")
    if pe_ratio is not None and 0 < pe_ratio < MAX_PE:
        reasons.append(f"PE {pe_ratio:.0f}")
    return reasons


def _default_fetch_fundamentals() -> FetchFundamentals:
    from data_provider.yfinance_fetcher import YfinanceFetcher

    fetcher = YfinanceFetcher()
    return fetcher.get_fundamentals


def _scan_tickers(tickers: List[str], fetch_fundamentals: FetchFundamentals) -> List[Tuple[str, Dict, List[str]]]:
    hits = []
    for ticker in tickers:
        try:
            fundamentals = fetch_fundamentals(ticker)
        except Exception as exc:
            logger.warning("Value radar fundamentals fetch failed for %s: %s", ticker, exc)
            continue
        if not fundamentals or not _passes_quality_gates(fundamentals):
            continue
        reasons = _fair_price_reasons(fundamentals)
        if reasons:
            hits.append((ticker, fundamentals, reasons))
    return hits


def scan_watchlist(tickers: List[str], fetch_fundamentals: Optional[FetchFundamentals] = None) -> List[Tuple[str, Dict, List[str]]]:
    fetch_fundamentals = fetch_fundamentals or _default_fetch_fundamentals()
    unique_tickers = sorted({t.strip().upper() for t in tickers if t and t.strip()})
    return _scan_tickers(unique_tickers, fetch_fundamentals)


def scan_discovery(
    exclude_tickers: List[str],
    fmp_api_key: str,
    fetch_fundamentals: Optional[FetchFundamentals] = None,
) -> List[Tuple[str, Dict, List[str]]]:
    if not fmp_api_key:
        return []

    from data_provider.fmp_provider import get_stock_screener

    exclude = {t.strip().upper() for t in exclude_tickers if t and t.strip()}
    candidates = get_stock_screener(fmp_api_key)
    candidate_tickers = [c["ticker"] for c in candidates if c["ticker"] not in exclude][:DISCOVERY_SCAN_LIMIT]

    fetch_fundamentals = fetch_fundamentals or _default_fetch_fundamentals()
    return _scan_tickers(candidate_tickers, fetch_fundamentals)


def _format_hit(ticker: str, fundamentals: Dict, reasons: List[str]) -> str:
    price = fundamentals.get("current_price")
    price_str = f"${price:.0f}" if price else ""
    roe = fundamentals.get("roe")
    roe_str = f"ROE {roe:.0f}%" if roe is not None else ""
    parts = [p for p in [price_str, " | ".join(reasons), roe_str] if p]
    return f"• **{ticker}** " + " | ".join(parts)


def build_value_radar_section(
    watchlist_tickers: List[str],
    fmp_api_key: str = "",
    max_chars: int = 800,
    fetch_fundamentals: Optional[FetchFundamentals] = None,
) -> str:
    """Build the 💎 价值雷达 bullet-list section, or "" if nothing qualifies."""
    try:
        watchlist_hits = scan_watchlist(watchlist_tickers, fetch_fundamentals)[:MAX_WATCHLIST_HITS]
        discovery_hits = scan_discovery(watchlist_tickers, fmp_api_key, fetch_fundamentals)[:MAX_DISCOVERY_HITS]
    except Exception as exc:
        logger.warning("Value radar scan failed: %s", exc)
        return ""

    lines = []
    for ticker, fundamentals, reasons in watchlist_hits:
        lines.append(_format_hit(ticker, fundamentals, reasons))
    for ticker, fundamentals, reasons in discovery_hits:
        lines.append(_format_hit(ticker, fundamentals, reasons) + " (新发现)")

    if not lines:
        return ""

    section = "\n".join(lines)
    while len(section) > max_chars and lines:
        lines.pop()
        section = "\n".join(lines)

    return section
