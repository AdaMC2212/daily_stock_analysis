# -*- coding: utf-8 -*-
"""
Telegram polling listener for on-demand stock analysis.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Dict, Optional

import requests

from src.core.pipeline import analyze_single_stock

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^(?:analyze|analyse)\s+([A-Za-z]{1,5})$", re.IGNORECASE)


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


def _send_message(token: str, chat_id: str, text: str) -> bool:
    if not text:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
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
        "- analyze TICKER  (or analyse TICKER)",
        "- portfolio",
        "- help",
    ])


def _build_portfolio_scorecard() -> str:
    state_path = Path(__file__).resolve().parent.parent.parent / "data" / "signal_history.json"
    if not state_path.exists():
        return "No portfolio history found yet."
    try:
        data = json.loads(state_path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return "Could not read portfolio history."

    lines = ["Portfolio scorecard:"]
    for ticker, info in sorted(data.items()):
        score = info.get("last_score", "N/A")
        decision = info.get("last_decision", "N/A")
        date = info.get("date", "N/A")
        lines.append(f"- {ticker}: {score} ({decision}) as of {date}")
    return "\n".join(lines)


def _build_analysis_reply(result) -> str:
    if not result:
        return "Could not find data for this ticker. Check the ticker and try again."

    date_str = time.strftime("%B %d %Y").replace(" 0", " ")
    name = getattr(result, "name", "")
    code = getattr(result, "code", "")
    score = getattr(result, "sentiment_score", "N/A")
    advice = getattr(result, "operation_advice", "N/A")
    trend = getattr(result, "trend_prediction", "")
    price = getattr(result, "current_price", None)
    price_text = f"${price:,.2f}" if isinstance(price, (int, float)) else "N/A"

    sniper = result.get_sniper_points() if hasattr(result, "get_sniper_points") else {}
    ideal_buy = sniper.get("ideal_buy", "N/A")
    stop_loss = sniper.get("stop_loss", "N/A")
    take_profit = sniper.get("take_profit", "N/A")

    summary = getattr(result, "analysis_summary", "") or ""
    risk = getattr(result, "risk_warning", "") or ""

    lines = [
        f"📊 {name} Analysis — {date_str}",
        "",
        f"💰 Price: {price_text}",
        f"📈 Score: {score}/100 — {advice}",
        f"🎯 Trend: {trend}" if trend else "🎯 Trend: N/A",
        "",
        f"💡 Verdict: {summary}" if summary else "💡 Verdict: N/A",
    ]

    if risk:
        lines.append("")
        lines.append(f"⚠️ Portfolio Warning: {risk}")

    lines.extend([
        "",
        f"🛑 Stop Loss if entering: {stop_loss}",
        f"✅ Take Profit target: {take_profit}",
        f"🎯 Ideal Buy: {ideal_buy}",
    ])
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

    match = _TICKER_RE.match(text)
    if not match:
        return

    ticker = match.group(1).upper()
    if not re.match(r"^[A-Z]{1,5}$", ticker):
        _send_message(token, chat_id, f"Invalid ticker format: {ticker}")
        return

    done_flag = {"done": False}

    def _late_notice() -> None:
        time.sleep(30)
        if not done_flag["done"]:
            _send_message(token, chat_id, f"Analyzing {ticker}... this takes about 30 seconds ⏳")

    threading.Thread(target=_late_notice, daemon=True).start()

    result = analyze_single_stock(ticker, include_portfolio_context=True)
    done_flag["done"] = True
    if result is None:
        _send_message(token, chat_id, f"Could not find data for {ticker}. Check the ticker and try again.")
        return
    _send_message(token, chat_id, _build_analysis_reply(result))


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
