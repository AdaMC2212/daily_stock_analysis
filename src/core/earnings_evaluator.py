# -*- coding: utf-8 -*-
"""
Earnings evaluator using FMP financials + Gemini analysis.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.analyzer import GeminiAnalyzer
from data_provider.fmp_provider import (
    get_income_statement,
    get_balance_sheet,
    get_cash_flow,
)

logger = logging.getLogger(__name__)


def evaluate_earnings(ticker: str, fmp_api_key: str) -> Optional[str]:
    if not ticker or not fmp_api_key:
        return None

    income = get_income_statement(ticker, fmp_api_key)
    balance = get_balance_sheet(ticker, fmp_api_key)
    cash_flow = get_cash_flow(ticker, fmp_api_key)
    if not income or not balance or not cash_flow:
        return None

    financials = {
        "ticker": ticker.upper(),
        "income": {
            "revenue": income.get("revenue"),
            "gross_margin_pct": income.get("gross_margin"),
            "net_profit_margin_pct": income.get("net_profit_margin"),
            "eps": income.get("eps"),
            "revenue_growth_yoy_pct": income.get("revenue_growth_yoy"),
        },
        "balance_sheet": {
            "current_ratio": balance.get("current_ratio"),
            "debt_to_equity": balance.get("debt_to_equity"),
        },
        "cash_flow": {
            "free_cash_flow": cash_flow.get("free_cash_flow"),
            "free_cash_flow_per_share": cash_flow.get("free_cash_flow_per_share"),
        },
    }

    prompt = (
        "You are evaluating an earnings report for a long-term "
        "retail investor who holds this stock.\n\n"
        "Here are the latest financials:\n"
        f"{json.dumps(financials, ensure_ascii=False)}\n\n"
        "Evaluate using these criteria:\n"
        "- Gross margin: is it above 40%? Is it improving or declining YoY?\n"
        "- Net profit margin: is it positive and growing?\n"
        "- EPS: beat or miss expectations? Growing YoY?\n"
        "- Current ratio: above 1.5 is healthy, below 1.0 is a warning\n"
        "- Debt to equity: above 2.0 is concerning for most companies\n"
        "- Free cash flow: positive is essential for long-term health\n\n"
        "Output format — use exactly this structure:\n"
        "VERDICT: [Strong / Decent / Weak / Concerning]\n"
        "HEADLINE: [One sentence summary of the most important finding]\n"
        "GROSS MARGIN: [value]% — [one sentence commentary]\n"
        "NET MARGIN: [value]% — [one sentence commentary]\n"
        "EPS: [value] — [one sentence commentary]\n"
        "CURRENT RATIO: [value] — [one sentence commentary]\n"
        "DEBT TO EQUITY: [value] — [one sentence commentary]\n"
        "FREE CASH FLOW: $[value]B — [one sentence commentary]\n"
        "LONG TERM TAKE: [2-3 sentences on what this means for "
        "a long-term holder of this stock]"
    )

    analyzer = GeminiAnalyzer()
    if not analyzer.is_available():
        logger.warning("Earnings evaluator: LLM not available.")
        return None

    return analyzer.generate_text(prompt, max_tokens=800, temperature=0.3)
