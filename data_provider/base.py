# -*- coding: utf-8 -*-
"""
Minimal data provider base layer for the current US-only runtime.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any

import pandas as pd

from src.analyzer import STOCK_NAME_MAP

logger = logging.getLogger(__name__)

STANDARD_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg"]


def unwrap_exception(exc: Exception) -> Exception:
    """Return the deepest chained exception without looping forever."""
    current = exc
    visited = set()

    while current is not None and id(current) not in visited:
        visited.add(id(current))
        next_exc = current.__cause__ or current.__context__
        if next_exc is None:
            break
        current = next_exc

    return current


def summarize_exception(exc: Exception) -> Tuple[str, str]:
    """Build a stable exception summary for logging."""
    root = unwrap_exception(exc)
    error_type = type(root).__name__
    message = str(exc).strip() or str(root).strip() or error_type
    return error_type, " ".join(message.split())


def normalize_stock_code(stock_code: str) -> str:
    """
    Normalize stock code by stripping exchange prefixes and suffixes where safe.

    US tickers are preserved as-is apart from whitespace trimming.
    """
    code = stock_code.strip()
    upper = code.upper()

    if upper.startswith(("SH", "SZ")) and not upper.startswith(("SH.", "SZ.")):
        candidate = code[2:]
        if candidate.isdigit() and len(candidate) in (5, 6):
            return candidate

    if upper.startswith("BJ") and not upper.startswith("BJ."):
        candidate = code[2:]
        if candidate.isdigit() and len(candidate) == 6:
            return candidate

    if "." in code:
        base, suffix = code.rsplit(".", 1)
        if suffix.upper() in ("SH", "SZ", "SS", "BJ") and base.isdigit():
            return base

    return code


def is_bse_code(code: str) -> bool:
    """Return whether a code matches known Beijing Stock Exchange formats."""
    base = (code or "").strip().split(".")[0]
    if len(base) != 6 or not base.isdigit():
        return False
    return base.startswith(("8", "4")) or base.startswith("92")


def canonical_stock_code(code: str) -> str:
    """Return a consistent uppercase representation for incoming stock codes."""
    return (code or "").strip().upper()


class DataFetchError(Exception):
    """Raised when a provider cannot return usable market data."""


class RateLimitError(DataFetchError):
    """Raised when a provider appears rate limited."""


class DataSourceUnavailableError(DataFetchError):
    """Raised when a provider is unavailable."""


class BaseFetcher(ABC):
    """Abstract base class for market-data fetchers."""

    name: str = "BaseFetcher"
    priority: int = 99

    @abstractmethod
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch raw data from the upstream source."""

    @abstractmethod
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """Normalize raw provider output into the shared schema."""

    def get_main_indices(self, region: str = "us") -> Optional[List[Dict[str, Any]]]:
        """Return realtime major-index data if supported by the provider."""
        return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """Return market breadth data if supported by the provider."""
        return None

    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """Return leading and lagging sectors if supported by the provider."""
        return None

    def get_daily_data(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 252,
    ) -> pd.DataFrame:
        """Fetch, normalize, clean, and enrich daily data."""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if start_date is None:
            start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=days * 2)
            start_date = start_dt.strftime("%Y-%m-%d")

        try:
            raw_df = self._fetch_raw_data(stock_code, start_date, end_date)
            if raw_df is None or raw_df.empty:
                raise DataFetchError(f"[{self.name}] no data returned for {stock_code}")

            df = self._normalize_data(raw_df, stock_code)
            df = self._clean_data(df)
            df = self._calculate_indicators(df)
            return df
        except Exception as exc:
            error_type, error_reason = summarize_exception(exc)
            raise DataFetchError(f"[{self.name}] {stock_code}: {error_type} {error_reason}") from exc

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply shared data cleaning to normalized OHLCV frames."""
        df = df.copy()

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        for col in ["open", "high", "low", "close", "volume", "amount", "pct_chg"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["close", "volume"])
        df = df.sort_values("date", ascending=True).reset_index(drop=True)
        return df

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add the technical indicators used by the current prompts."""
        df = df.copy()
        df["ma5"] = df["close"].rolling(window=5, min_periods=1).mean()
        df["ma10"] = df["close"].rolling(window=10, min_periods=1).mean()
        df["ma20"] = df["close"].rolling(window=20, min_periods=1).mean()
        df["ma60"] = df["close"].rolling(window=60, min_periods=1).mean()
        df["ma120"] = df["close"].rolling(window=120, min_periods=1).mean()
        df["ma200"] = df["close"].rolling(window=200, min_periods=1).mean()
        df["high_52w"] = df["close"].rolling(window=252, min_periods=1).max()
        df["low_52w"] = df["close"].rolling(window=252, min_periods=1).min()

        avg_volume_5 = df["volume"].rolling(window=5, min_periods=1).mean()
        df["volume_ratio"] = df["volume"] / avg_volume_5.shift(1)
        df["volume_ratio"] = df["volume_ratio"].fillna(1.0)

        for col in ["ma5", "ma10", "ma20", "ma60", "ma120", "ma200", "high_52w", "low_52w", "volume_ratio"]:
            df[col] = df[col].round(2)

        return df

    def get_fundamentals(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """Return provider-specific fundamentals when available."""
        return None


class DataFetcherManager:
    """
    US-only data provider manager.

    The current supported runtime uses Yahoo Finance for:
    - US stock daily history
    - US stock realtime quotes
    - US major index market review data
    """

    def __init__(self, fetchers: Optional[List[BaseFetcher]] = None):
        self._fetchers: List[BaseFetcher] = sorted(fetchers, key=lambda f: f.priority) if fetchers else []
        if not self._fetchers:
            self._init_default_fetchers()
        self._stock_name_cache: Dict[str, str] = {}

    def _init_default_fetchers(self) -> None:
        """Initialize the only provider retained for the current project scope."""
        from .yfinance_fetcher import YfinanceFetcher

        self._fetchers = [YfinanceFetcher()]
        logger.info("Initialized data providers: YfinanceFetcher")

    def add_fetcher(self, fetcher: BaseFetcher) -> None:
        """Add a custom fetcher, mainly for tests or local experimentation."""
        self._fetchers.append(fetcher)
        self._fetchers.sort(key=lambda f: f.priority)

    @property
    def available_fetchers(self) -> List[str]:
        """Return configured fetcher names."""
        return [f.name for f in self._fetchers]

    def get_daily_data(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 252,
    ) -> Tuple[pd.DataFrame, str]:
        """Fetch daily history using the retained provider stack."""
        stock_code = normalize_stock_code(stock_code)
        errors: List[str] = []

        for fetcher in self._fetchers:
            try:
                df = fetcher.get_daily_data(stock_code, start_date=start_date, end_date=end_date, days=days)
                if df is not None and not df.empty:
                    return df, fetcher.name
            except Exception as exc:
                error_type, error_reason = summarize_exception(exc)
                errors.append(f"[{fetcher.name}] ({error_type}) {error_reason}")

        raise DataFetchError(f"Failed to fetch daily data for {stock_code}: {'; '.join(errors)}")

    def get_realtime_quote(self, stock_code: str):
        """Fetch realtime quote data using the retained provider stack."""
        stock_code = normalize_stock_code(stock_code)

        for fetcher in self._fetchers:
            if hasattr(fetcher, "get_realtime_quote"):
                try:
                    quote = fetcher.get_realtime_quote(stock_code)
                    if quote is not None:
                        return quote
                except Exception as exc:
                    logger.warning("Realtime quote fetch failed for %s via %s: %s", stock_code, fetcher.name, exc)

        return None

    def get_fundamentals(self, stock_code: str) -> Dict[str, Any]:
        """Fetch fundamentals using the retained provider stack when supported."""
        stock_code = normalize_stock_code(stock_code)

        for fetcher in self._fetchers:
            if hasattr(fetcher, "get_fundamentals"):
                try:
                    data = fetcher.get_fundamentals(stock_code)
                    if data:
                        return data
                except Exception as exc:
                    logger.warning("Fundamental fetch failed for %s via %s: %s", stock_code, fetcher.name, exc)

        return {}

    def get_chip_distribution(self, stock_code: str):
        """Chip distribution is not part of the current US-only provider stack."""
        return None

    def get_stock_name(self, stock_code: str, allow_realtime: bool = True) -> Optional[str]:
        """Resolve a stock display name from cache, prompt map, or realtime quote."""
        stock_code = normalize_stock_code(stock_code)

        if stock_code in STOCK_NAME_MAP:
            return STOCK_NAME_MAP[stock_code]

        if stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]

        if allow_realtime:
            quote = self.get_realtime_quote(stock_code)
            if quote and getattr(quote, "name", None):
                self._stock_name_cache[stock_code] = quote.name
                return quote.name

        return ""

    def prefetch_stock_names(self, stock_codes: List[str], use_bulk: bool = False) -> None:
        """Warm the stock-name cache using the supported realtime path."""
        del use_bulk
        for code in stock_codes:
            self.get_stock_name(code, allow_realtime=False)

    def batch_get_stock_names(self, stock_codes: List[str]) -> Dict[str, str]:
        """Return stock names for the provided codes."""
        result: Dict[str, str] = {}
        for code in stock_codes:
            name = self.get_stock_name(code)
            if name:
                result[code] = name
        return result

    def get_main_indices(self, region: str = "us") -> List[Dict[str, Any]]:
        """Return major index data for the requested region."""
        for fetcher in self._fetchers:
            try:
                data = fetcher.get_main_indices(region=region)
                if data:
                    return data
            except Exception as exc:
                logger.warning("Major index fetch failed via %s: %s", fetcher.name, exc)
        return []

    def get_market_stats(self) -> Dict[str, Any]:
        """Return market breadth data when available."""
        for fetcher in self._fetchers:
            try:
                data = fetcher.get_market_stats()
                if data:
                    return data
            except Exception as exc:
                logger.warning("Market stats fetch failed via %s: %s", fetcher.name, exc)
        return {}

    def get_sector_rankings(self, n: int = 5) -> Tuple[List[Dict], List[Dict]]:
        """Return sector rankings when available."""
        for fetcher in self._fetchers:
            try:
                data = fetcher.get_sector_rankings(n)
                if data:
                    return data
            except Exception as exc:
                logger.warning("Sector ranking fetch failed via %s: %s", fetcher.name, exc)
        return [], []
