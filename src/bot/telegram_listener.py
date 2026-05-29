# -*- coding: utf-8 -*-
"""
Telegram polling listener for portfolio snapshot and help commands.

Single-stock analysis (`analyze TICKER`) lives in the separate analyzer bot repo.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

import requests

from src.config import get_config
from src.portfolio.google_sheets_reader import load_portfolio_from_config

logger = logging.getLogger(__name__)


def _state_path() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return root / "data" / "bot_state.json"


def _load_state(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _save_state(path: Path, state: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _send_message(token: str, chat_id: str, text: str, parse_mode: Optional[str] = None) -> bool:
    if not text:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logger.warning("Telegram send failed: status=%s response=%s", resp.status_code, resp.text)
        return False
    except Exception as exc:
        logger.warning("Telegram send exception: %s", exc)
        return False


def _build_help() -> str:
    return "\n".join([
        "Available commands:",
        "- portfolio",
        "- help",
    ])


def _build_portfolio_scorecard() -> str:
    config = get_config()
    portfolio = load_portfolio_from_config(config)

    if not portfolio:
        return (
            "📊 Portfolio\n\n"
            "No portfolio data found. Check that GOOGLE_CREDENTIALS_JSON "
            "and GOOGLE_SHEET_ID are configured correctly."
        )

    total_value = sum(
        float(v.get("total_value") or 0)
        for v in portfolio.values()
    )
    total_pnl = sum(
        float(v.get("pnl") or 0)
        for v in portfolio.values()
    )
    total_cost = sum(
        float(v.get("shares") or 0) * float(v.get("avg_buy_price") or 0)
        for v in portfolio.values()
    )
    overall_pnl_pct = (
        (total_pnl / total_cost * 100) if total_cost > 0 else 0.0
    )

    pnl_sign = "+" if total_pnl >= 0 else ""
    lines = [
        "📊 Portfolio",
        "",
        f"💼 Total Value: ${total_value:,.0f}",
        f"📈 Overall P&L: {pnl_sign}${total_pnl:,.0f} "
        f"({pnl_sign}{overall_pnl_pct:.1f}%)",
        "",
    ]

    sorted_holdings = sorted(
        portfolio.items(),
        key=lambda kv: float(kv[1].get("allocation_pct") or 0),
        reverse=True,
    )

    for ticker, data in sorted_holdings:
        alloc = float(data.get("allocation_pct") or 0)
        pnl_pct = data.get("pnl_pct")
        avg_price = data.get("avg_buy_price")
        current_price = data.get("current_price")

        if pnl_pct is not None:
            try:
                pnl_val = float(pnl_pct)
                sign = "+" if pnl_val >= 0 else ""
                emoji = "✅" if pnl_val >= 5 else (
                    "🔴" if pnl_val <= -5 else "⚠️"
                )
                pnl_str = f"{sign}{pnl_val:.1f}%"
            except (TypeError, ValueError):
                pnl_str = "N/A"
                emoji = "⚠️"
        else:
            pnl_str = "N/A"
            emoji = "⚠️"

        avg_str = (
            f"${float(avg_price):,.2f}"
            if avg_price is not None else "N/A"
        )
        curr_str = (
            f"${float(current_price):,.2f}"
            if current_price is not None else "N/A"
        )

        lines.append(
            f"{emoji} {ticker} ({alloc:.1f}%) | "
            f"avg {avg_str} → {curr_str} | {pnl_str}"
        )

    return "\n".join(lines)


def _handle_message(token: str, chat_id: str, text: str) -> None:
    if not text:
        return
    text = text.strip()
    if text.lower() == "help":
        _send_message(token, chat_id, _build_help())
        return
    if text.lower() == "portfolio":
        _send_message(token, chat_id, _build_portfolio_scorecard())
        return

    if text.lower().startswith(("analyze", "analyse")):
        _send_message(
            token,
            chat_id,
            "Single-stock analysis moved to the dedicated analyzer bot. Send 'analyze TICKER' there.",
        )
        return


def _poll_loop() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.warning("BOT_LISTENER: Telegram token/chat_id not configured; listener disabled.")
        return

    poll_interval = int(os.getenv("BOT_LISTENER_POLL_INTERVAL", "5") or 5)
    state_path = _state_path()
    state = _load_state(state_path)
    offset = state.get("last_update_id", 0)

    logger.info("BOT_LISTENER: started polling every %ss", poll_interval)
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"timeout": 10, "offset": offset + 1}
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                logger.warning("BOT_LISTENER: getUpdates failed: %s %s", resp.status_code, resp.text)
                time.sleep(poll_interval)
                continue
            payload = resp.json()
            updates = payload.get("result", []) if isinstance(payload, dict) else []
            for update in updates:
                update_id = update.get("update_id")
                message = update.get("message") or {}
                msg_chat_id = str(message.get("chat", {}).get("id", ""))
                text = message.get("text", "")
                if msg_chat_id != chat_id:
                    offset = max(offset, update_id or offset)
                    continue
                _handle_message(token, chat_id, text)
                if update_id is not None:
                    offset = max(offset, update_id)
            state["last_update_id"] = offset
            _save_state(state_path, state)
        except Exception as exc:
            logger.warning("BOT_LISTENER: polling error: %s", exc)
        time.sleep(poll_interval)


def start_listener() -> None:
    thread = threading.Thread(target=_poll_loop, daemon=True)
    thread.start()
