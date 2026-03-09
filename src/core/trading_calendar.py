# -*- coding: utf-8 -*-
"""
Trading-calendar helpers for US-market scheduling and reference-date selection.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional, Set
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_XCALS_AVAILABLE = False
try:
    import exchange_calendars as xcals

    _XCALS_AVAILABLE = True
except ImportError:
    logger.warning(
        "exchange-calendars not installed; trading day checks will fail open. "
        "Run: pip install exchange-calendars"
    )

MARKET_EXCHANGE = {"us": "XNYS"}
MARKET_TIMEZONE = {"us": "America/New_York"}


@lru_cache(maxsize=len(MARKET_EXCHANGE))
def _get_calendar(exchange_code: str):
    """Cache exchange-calendars lookup objects."""
    if not _XCALS_AVAILABLE:
        return None
    return xcals.get_calendar(exchange_code)


def get_market_for_stock(code: str) -> Optional[str]:
    """Infer the market region for a symbol."""
    if not code or not isinstance(code, str):
        return None

    code = (code or "").strip().upper()
    from data_provider import is_us_index_code, is_us_stock_code

    if is_us_stock_code(code) or is_us_index_code(code):
        return "us"
    return None


def is_market_open(market: str, check_date: date) -> bool:
    """Return whether the market has a trading session on the given date."""
    if not _XCALS_AVAILABLE:
        return True

    exchange_code = MARKET_EXCHANGE.get(market)
    if not exchange_code:
        return True

    try:
        cal = _get_calendar(exchange_code)
        session = datetime(check_date.year, check_date.month, check_date.day)
        return bool(cal.is_session(session))
    except Exception as exc:
        logger.warning("trading_calendar.is_market_open fail-open for %s: %s", market, exc)
        return True


def previous_business_day(market: str, start_date: date) -> date:
    """Return the previous trading session for the given market."""
    candidate = start_date - timedelta(days=1)
    for _ in range(10):
        if is_market_open(market, candidate):
            return candidate
        candidate -= timedelta(days=1)
    return start_date - timedelta(days=1)


def get_market_reference_date(
    market: str,
    run_timezone: str = "UTC",
    now: Optional[datetime] = None,
) -> date:
    """Resolve the trading date that should be analyzed for the current run.

    For post-market runs in an Asia timezone (for example 08:00 MYT), the local
    calendar date is already the next day while the relevant US market session
    is still the previous US trading day. When the run timezone's local date is
    ahead of the market-local date, this helper maps the run to the previous
    valid market session for that local date.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    market_zone = ZoneInfo(MARKET_TIMEZONE.get(market, "UTC"))
    run_zone = ZoneInfo(run_timezone)

    market_now = now.astimezone(market_zone)
    run_now = now.astimezone(run_zone)
    market_date = market_now.date()

    if run_now.date() > market_date:
        return previous_business_day(market, run_now.date())
    return market_date


def get_open_markets_today(
    run_timezone: str = "UTC",
    now: Optional[datetime] = None,
) -> Set[str]:
    """Return markets whose reference trading date is open for this run."""
    if not _XCALS_AVAILABLE:
        return {"us"}

    result: Set[str] = set()
    for market in MARKET_TIMEZONE:
        try:
            reference_date = get_market_reference_date(market, run_timezone=run_timezone, now=now)
            if is_market_open(market, reference_date):
                result.add(market)
        except Exception as exc:
            logger.warning("get_open_markets_today fail-open for %s: %s", market, exc)
            result.add(market)
    return result


def compute_effective_region(config_region: str, open_markets: Set[str]) -> Optional[str]:
    """Return the effective market-review region based on open markets."""
    _ = config_region
    return "us" if "us" in open_markets else ""
