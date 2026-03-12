# -*- coding: utf-8 -*-
"""
Financial Modeling Prep provider for earnings evaluation.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
import os

logger = logging.getLogger(__name__)

BASE_URL = "https://financialmodelingprep.com/api/v3"
_CACHE_TTL_SECONDS = 24 * 60 * 60


def _cache_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    return root / "data" / "fmp_cache.json"


def _load_cache() -> Dict:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _save_cache(cache: Dict) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _get_cached(key: str) -> Optional[Dict]:
    cache = _load_cache()
    entry = cache.get(key)
    if not entry:
        return None
    ts = entry.get("timestamp")
    if not ts or time.time() - float(ts) > _CACHE_TTL_SECONDS:
        return None
    return entry.get("data")


def _set_cached(key: str, data: Dict) -> None:
    cache = _load_cache()
    cache[key] = {"timestamp": time.time(), "data": data}
    _save_cache(cache)


def _get_json(url: str) -> Optional[Dict]:
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            logger.warning("FMP request failed: %s %s", resp.status_code, resp.text)
            return None
        return resp.json()
    except Exception as exc:
        logger.warning("FMP request error: %s", exc)
        return None


def get_income_statement(ticker: str, api_key: str) -> Optional[Dict]:
    key = f"income_statement:{ticker.upper()}"
    cached = _get_cached(key)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/income-statement/{ticker.upper()}?limit=2&apikey={api_key}"
    data = _get_json(url)
    if not data or not isinstance(data, list):
        return None
    try:
        latest = data[0]
        previous = data[1] if len(data) > 1 else None
        revenue = float(latest.get("revenue") or 0)
        gross_profit = float(latest.get("grossProfit") or 0)
        net_income = float(latest.get("netIncome") or 0)
        eps = latest.get("eps") or latest.get("epsdiluted") or latest.get("epsDiluted")
        eps = float(eps) if eps is not None else None

        gross_margin = (gross_profit / revenue * 100) if revenue else None
        net_margin = (net_income / revenue * 100) if revenue else None

        revenue_growth_yoy = None
        if previous:
            prev_revenue = float(previous.get("revenue") or 0)
            if prev_revenue:
                revenue_growth_yoy = (revenue - prev_revenue) / prev_revenue * 100

        result = {
            "revenue": revenue or None,
            "gross_profit": gross_profit or None,
            "gross_margin": gross_margin,
            "net_income": net_income or None,
            "net_profit_margin": net_margin,
            "eps": eps,
            "revenue_growth_yoy": revenue_growth_yoy,
        }
        _set_cached(key, result)
        return result
    except Exception as exc:
        logger.warning("FMP income statement parse error: %s", exc)
        return None


def get_balance_sheet(ticker: str, api_key: str) -> Optional[Dict]:
    key = f"balance_sheet:{ticker.upper()}"
    cached = _get_cached(key)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/balance-sheet-statement/{ticker.upper()}?limit=1&apikey={api_key}"
    data = _get_json(url)
    if not data or not isinstance(data, list):
        return None
    try:
        latest = data[0]
        current_assets = float(latest.get("totalCurrentAssets") or 0)
        current_liabilities = float(latest.get("totalCurrentLiabilities") or 0)
        total_debt = float(latest.get("totalDebt") or 0)
        total_equity = float(latest.get("totalStockholdersEquity") or 0)

        current_ratio = (current_assets / current_liabilities) if current_liabilities else None
        debt_to_equity = (total_debt / total_equity) if total_equity else None

        result = {
            "total_current_assets": current_assets or None,
            "total_current_liabilities": current_liabilities or None,
            "current_ratio": current_ratio,
            "total_debt": total_debt or None,
            "total_equity": total_equity or None,
            "debt_to_equity": debt_to_equity,
        }
        _set_cached(key, result)
        return result
    except Exception as exc:
        logger.warning("FMP balance sheet parse error: %s", exc)
        return None


def get_cash_flow(ticker: str, api_key: str) -> Optional[Dict]:
    key = f"cash_flow:{ticker.upper()}"
    cached = _get_cached(key)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/cash-flow-statement/{ticker.upper()}?limit=1&apikey={api_key}"
    data = _get_json(url)
    if not data or not isinstance(data, list):
        return None
    try:
        latest = data[0]
        operating_cf = float(latest.get("operatingCashFlow") or 0)
        capex = float(latest.get("capitalExpenditure") or 0)
        free_cf = operating_cf - capex
        fcf_per_share = latest.get("freeCashFlowPerShare")
        fcf_per_share = float(fcf_per_share) if fcf_per_share is not None else None

        result = {
            "operating_cash_flow": operating_cf or None,
            "capital_expenditure": capex or None,
            "free_cash_flow": free_cf,
            "free_cash_flow_per_share": fcf_per_share,
        }
        _set_cached(key, result)
        return result
    except Exception as exc:
        logger.warning("FMP cash flow parse error: %s", exc)
        return None


def get_earnings_calendar(tickers: List[str], api_key: str) -> List[str]:
    key = "earnings_calendar"
    cached = _get_cached(key)
    data = cached
    if data is None:
        url = f"{BASE_URL}/earning_calendar?apikey={api_key}"
        data = _get_json(url)
        if data is None:
            return []
        _set_cached(key, {"raw": data})

    raw = data.get("raw") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []

    lookback_days = int(os.getenv("EARNINGS_LOOKBACK_DAYS", "7") or 7)
    cutoff = datetime.now().date() - timedelta(days=lookback_days)
    tickers_set = {t.strip().upper() for t in tickers if t and t.strip()}
    reported = []
    for item in raw:
        symbol = (item.get("symbol") or "").upper()
        if symbol not in tickers_set:
            continue
        date_str = item.get("date") or ""
        try:
            report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            continue
        if report_date >= cutoff:
            reported.append(symbol)
    return sorted(set(reported))
