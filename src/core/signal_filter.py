# -*- coding: utf-8 -*-
"""
Signal filtering utilities for buy alerts and daily digest.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


_ALERT_ADVICE = {"Accumulate", "買入", "加仓", "买入"}


@dataclass
class FilterConfig:
    min_score: int
    alert_enabled: bool
    daily_digest_enabled: bool


@dataclass
class FilteredSignals:
    alert_results: List
    digest_results: List


def _parse_bool(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    v = value.strip().lower()
    if not v:
        return default
    return v not in {"0", "false", "no", "off"}


def get_filter_config() -> FilterConfig:
    return FilterConfig(
        min_score=int(os.getenv("BUY_ALERT_MIN_SCORE", "70") or 70),
        alert_enabled=_parse_bool(os.getenv("BUY_ALERT_ENABLED", "true"), default=True),
        daily_digest_enabled=_parse_bool(os.getenv("DAILY_DIGEST_ENABLED", "true"), default=True),
    )


def _history_path() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return root / "data" / "signal_history.json"


def _load_history(path: Path) -> Dict[str, Dict]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _save_history(path: Path, history: Dict[str, Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def _is_alert_candidate(result, min_score: int) -> bool:
    score = getattr(result, "sentiment_score", None)
    if score is None or score < min_score:
        return False
    if getattr(result, "decision_type", "") != "buy":
        return False
    advice = getattr(result, "operation_advice", "")
    return advice in _ALERT_ADVICE


def _passes_consecutive_day_check(
    result,
    history: Dict[str, Dict],
    today_str: str,
    min_score: int,
) -> bool:
    ticker = getattr(result, "code", "").upper()
    prev = history.get(ticker)
    if not prev:
        return False
    prev_date = prev.get("date")
    prev_score = prev.get("last_score")
    prev_decision = prev.get("last_decision")
    try:
        yesterday = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        return False
    if prev_date != yesterday:
        return False
    try:
        prev_score_val = float(prev_score)
    except (TypeError, ValueError):
        return False
    if prev_score_val < min_score:
        return False
    return prev_decision == "buy"


def filter_signals(results: List, min_score: int, alert_enabled: bool) -> FilteredSignals:
    digest_results = list(results or [])
    if not results:
        return FilteredSignals(alert_results=[], digest_results=[])

    history_path = _history_path()
    history = _load_history(history_path)
    today_str = datetime.now().strftime("%Y-%m-%d")

    alert_results: List = []
    for result in results:
        if alert_enabled and _is_alert_candidate(result, min_score):
            if _passes_consecutive_day_check(result, history, today_str, min_score):
                alert_results.append(result)

        ticker = getattr(result, "code", "").upper()
        history[ticker] = {
            "last_score": getattr(result, "sentiment_score", None),
            "last_decision": getattr(result, "decision_type", None),
            "date": today_str,
        }

    _save_history(history_path, history)

    return FilteredSignals(alert_results=alert_results, digest_results=digest_results)
