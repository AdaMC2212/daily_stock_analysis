# -*- coding: utf-8 -*-
"""
Budget allocation tracker for monthly cash deployment.

Tracks monthly budget usage and suggests per-buy deployment amounts.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import Config, get_config

logger = logging.getLogger(__name__)


def _default_state_path() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return root / "data" / "budget_state.json"


@dataclass
class BudgetState:
    month: str
    total_budget: float
    deployed: float
    buys: int


class BudgetTracker:
    def __init__(
        self,
        monthly_budget: float,
        deposit_day: int,
        state_path: Optional[Path] = None,
        confluence_threshold: int = 70,
        exceptional_threshold: int = 85,
        first_buy_pct: float = 0.45,
        second_buy_pct: float = 0.30,
    ) -> None:
        self.monthly_budget = max(0.0, float(monthly_budget or 0))
        self.deposit_day = int(deposit_day or 1)
        self.confluence_threshold = int(confluence_threshold)
        self.exceptional_threshold = int(exceptional_threshold)
        self.first_buy_pct = float(first_buy_pct)
        self.second_buy_pct = float(second_buy_pct)
        self.state_path = state_path or _default_state_path()
        self._lock = threading.Lock()
        self._state = self._load_state()
        self._ensure_current_month()

    @property
    def enabled(self) -> bool:
        return self.monthly_budget > 0

    def suggest_deployment(self, score: Optional[float], is_buy_signal: bool) -> Optional[Dict[str, float]]:
        if not self.enabled or not is_buy_signal or score is None:
            return None
        if float(score) < self.confluence_threshold:
            return None

        with self._lock:
            self._ensure_current_month()

            remaining = max(0.0, self._state.total_budget - self._state.deployed)
            if remaining <= 0:
                return None

            deploy = 0.0
            if self._state.buys == 0:
                deploy = self._state.total_budget * self.first_buy_pct
            elif self._state.buys == 1:
                deploy = self._state.total_budget * self.second_buy_pct
            else:
                if float(score) < self.exceptional_threshold:
                    return None
                deploy = remaining

            deploy = max(0.0, min(deploy, remaining))
            if deploy <= 0:
                return None

            self._state.deployed += deploy
            self._state.buys += 1
            self._save_state()

            remaining_after = max(0.0, self._state.total_budget - self._state.deployed)
            return {
                "deploy_amount": round(deploy, 2),
                "total_budget": round(self._state.total_budget, 2),
                "remaining_after": round(remaining_after, 2),
            }

    def _ensure_current_month(self) -> None:
        current_month = datetime.now().strftime("%Y-%m")
        if (
            self._state.month != current_month
            or abs(self._state.total_budget - self.monthly_budget) > 0.0001
        ):
            self._state = BudgetState(
                month=current_month,
                total_budget=self.monthly_budget,
                deployed=0.0,
                buys=0,
            )
            self._save_state()

    def _load_state(self) -> BudgetState:
        current_month = datetime.now().strftime("%Y-%m")
        if not self.state_path.exists():
            return BudgetState(month=current_month, total_budget=self.monthly_budget, deployed=0.0, buys=0)

        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8") or "{}")
            return BudgetState(
                month=str(raw.get("month") or current_month),
                total_budget=float(raw.get("total_budget") or self.monthly_budget),
                deployed=float(raw.get("deployed") or 0.0),
                buys=int(raw.get("buys") or 0),
            )
        except Exception as exc:
            logger.warning("Failed to load budget state, resetting: %s", exc)
            return BudgetState(month=current_month, total_budget=self.monthly_budget, deployed=0.0, buys=0)

    def _save_state(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            payload: Dict[str, Any] = {
                "month": self._state.month,
                "total_budget": self._state.total_budget,
                "deployed": self._state.deployed,
                "buys": self._state.buys,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save budget state: %s", exc)


_budget_tracker: Optional[BudgetTracker] = None


def init_budget_tracker(config: Optional[Config] = None) -> Optional[BudgetTracker]:
    global _budget_tracker
    if _budget_tracker is not None:
        return _budget_tracker
    cfg = config or get_config()
    tracker = BudgetTracker(
        monthly_budget=getattr(cfg, "monthly_budget", 0.0),
        deposit_day=getattr(cfg, "monthly_deposit_date", 1),
    )
    if not tracker.enabled:
        return None
    _budget_tracker = tracker
    return _budget_tracker


def get_budget_tracker() -> Optional[BudgetTracker]:
    return _budget_tracker
