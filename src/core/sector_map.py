# -*- coding: utf-8 -*-
"""
Hardcoded sector map for common US tickers.
"""

from __future__ import annotations

from typing import List, Optional

SECTOR_MAP = {
    "AAPL": "tech",
    "MSFT": "tech",
    "NVDA": "tech",
    "GOOGL": "tech",
    "META": "tech",
    "AMZN": "tech",
    "TSLA": "tech",
    "AMD": "tech",
    "INTC": "tech",
    "SPY": "broad_market",
    "QQQ": "tech_etf",
    "VTI": "broad_market",
    "JPM": "financials",
    "BAC": "financials",
    "GS": "financials",
    "JNJ": "healthcare",
    "PFE": "healthcare",
    "XOM": "energy",
    "CVX": "energy",
    "BRK.B": "financials",
}


def get_sector(ticker: str) -> str:
    if not ticker:
        return "unknown"
    return SECTOR_MAP.get(ticker.strip().upper(), "unknown")


def get_concentration_warning(
    watchlist: List[str],
    new_ticker: str,
    threshold: int,
) -> Optional[str]:
    if not new_ticker:
        return None
    clean_watchlist = [t.strip().upper() for t in watchlist if t and t.strip()]
    new_sector = get_sector(new_ticker)
    if new_sector == "unknown":
        return None

    matching = [t for t in clean_watchlist if get_sector(t) == new_sector]
    total = len(clean_watchlist)
    percentage = (len(matching) + 1) / (total + 1) * 100
    if percentage <= threshold:
        return None

    tickers = matching + [new_ticker.strip().upper()]
    tickers_text = ", ".join(tickers)
    return (
        f"⚠️ Adding {new_ticker.upper()} would make you {percentage:.0f}% concentrated in "
        f"{new_sector} ({tickers_text}). Consider diversifying."
    )
