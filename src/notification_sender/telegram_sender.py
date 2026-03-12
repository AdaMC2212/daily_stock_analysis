import logging
import re
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_MARKDOWN_V2_SPECIALS = r"_*[]()~`>#+-=|{}.!"


def _escape_markdown_v2(text: str) -> str:
    if text is None:
        return ""
    escaped = text.replace("\\", "\\\\")
    return re.sub(rf"([{re.escape(_MARKDOWN_V2_SPECIALS)}])", r"\\\1", escaped)


def _format_price(value: Optional[float]) -> str:
    if value is None:
        return "暂无"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return "暂无"
    if val.is_integer():
        return f"${val:,.0f}"
    return f"${val:,.2f}"


def _format_money(value: Optional[float]) -> str:
    if value is None:
        return "暂无"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return "暂无"
    return f"${val:,.0f}"


def _format_money_signed(value: Optional[float]) -> str:
    if value is None:
        return "暂无"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return "暂无"
    sign = "+" if val >= 0 else "-"
    return f"{sign}${abs(val):,.0f}"


def _format_pct(value: Optional[float], with_sign: bool = False) -> str:
    if value is None:
        return "暂无"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return "暂无"
    fmt = "+.1f" if with_sign else ".1f"
    return f"{val:{fmt}}%"


def _format_shares(value: Optional[float]) -> str:
    if value is None:
        return "暂无"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return "暂无"
    if val.is_integer():
        return f"{val:.0f}"
    return f"{val:.2f}"


def _format_allocation(value: Optional[float]) -> str:
    if value is None:
        return "暂无"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return "暂无"
    return f"{val:.0f}%"


def _format_advice(advice: str) -> str:
    mapping = {
        "Accumulate": "加仓",
        "Hold": "持有",
        "Trim": "减仓",
        "Exit": "卖出",
        "Watch": "观望",
        "买入": "买入",
        "加仓": "加仓",
        "持有": "持有",
        "减仓": "减仓",
        "卖出": "卖出",
        "观望": "观望",
    }
    return mapping.get((advice or "").strip(), advice or "观望")


def _pick_pnl_emoji(pnl_pct: Optional[float]) -> str:
    if pnl_pct is None:
        return "⚠️"
    try:
        val = float(pnl_pct)
    except (TypeError, ValueError):
        return "⚠️"
    if val >= 5:
        return "✅"
    if val <= -5:
        return "🔴"
    return "⚠️"


def _safe_text(value: Optional[str]) -> str:
    if value is None:
        return "暂无"
    text = str(value).strip()
    return text if text else "暂无"


class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._base_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def _send(self, text: str) -> bool:
        try:
            payload = {
                "chat_id": self._chat_id,
                "text": _escape_markdown_v2(text),
                "parse_mode": "MarkdownV2",
            }
            response = requests.post(self._base_url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            logger.error("Telegram send failed: status=%s, response=%s", response.status_code, response.text)
            return False
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    def send_text(self, text: str, max_chars: int = 3000) -> bool:
        if text is None:
            return False
        content = text.strip()
        if not content:
            return False

        lines = content.splitlines()
        chunks: List[str] = []
        current = ""
        for line in lines:
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
                current = line
                continue
            # Single line exceeds max length; split hard.
            for i in range(0, len(line), max_chars):
                chunks.append(line[i:i + max_chars])
            current = ""
        if current:
            chunks.append(current)

        success = True
        for chunk in chunks:
            success = self._send(chunk) and success
        return success

    def send_buy_alert(self, alert_message: str) -> bool:
        if alert_message is None:
            return False
        message = alert_message.strip()
        if not message:
            return False
        return self._send(f"⚡ ALERT\n\n{message}")

    def send_daily_digest(self, digest_message: str) -> bool:
        if digest_message is None:
            return False
        message = digest_message.strip()
        if not message:
            return False
        return self._send(message)

    def send_portfolio_snapshot(self, portfolio: Dict[str, Dict]) -> bool:
        if not portfolio:
            content = "📊 *持仓快照*\n\n暂无持仓数据"
            return self._send(content)

        total_value = 0.0
        total_pnl = 0.0
        total_cost = 0.0
        value_seen = False
        pnl_seen = False
        for item in portfolio.values():
            if item.get("total_value") is not None:
                total_value += float(item["total_value"])
                value_seen = True
            if item.get("pnl") is not None:
                total_pnl += float(item["pnl"])
                pnl_seen = True
            if item.get("shares") is not None and item.get("avg_buy_price") is not None:
                total_cost += float(item["shares"]) * float(item["avg_buy_price"])

        total_value_text = _format_money(total_value) if value_seen else "暂无"
        total_pnl_text = _format_money_signed(total_pnl) if pnl_seen else "暂无"
        total_pnl_pct = None
        if total_cost > 0 and pnl_seen:
            total_pnl_pct = (total_pnl / total_cost) * 100
        total_pnl_pct_text = _format_pct(total_pnl_pct, with_sign=True) if total_pnl_pct is not None else "暂无"

        lines = [
            "📊 *持仓快照*",
            "",
            f"💼 总市值: {total_value_text} | 总盈亏: {total_pnl_text} ({total_pnl_pct_text})",
            "",
        ]

        def sort_key(item: Dict) -> float:
            value = item.get("allocation_pct")
            try:
                return float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        for ticker, item in sorted(portfolio.items(), key=lambda kv: sort_key(kv[1]), reverse=True):
            alloc = _format_allocation(item.get("allocation_pct"))
            avg_price = _format_price(item.get("avg_buy_price"))
            current_price = _format_price(item.get("current_price"))
            pnl_pct = item.get("pnl_pct")
            pnl_pct_text = _format_pct(pnl_pct, with_sign=True)
            emoji = _pick_pnl_emoji(pnl_pct)
            lines.append(f"{ticker}  {alloc} | 均价{avg_price}  | 现价{current_price}  | {pnl_pct_text} {emoji}")

        return self._send("\n".join(lines))

    def send_stock_card(
        self,
        result,
        position: Optional[Dict],
        tier: int,
        is_deposit_month: bool,
        budget_suggestion: Optional[Dict] = None,
    ) -> bool:
        ticker = getattr(result, "code", "")
        score = getattr(result, "sentiment_score", None)
        advice = _format_advice(getattr(result, "operation_advice", "观望"))
        score_text = "暂无" if score is None else str(score)

        lines = [f"📈 *{ticker}* — 评分: {score_text} | {advice}"]

        if position:
            shares = _format_shares(position.get("shares"))
            avg_buy = _format_price(position.get("avg_buy_price"))
            pnl_pct = _format_pct(position.get("pnl_pct"), with_sign=True)
            pnl_value = _format_money_signed(position.get("pnl"))
            lines.append(f"💼 持仓: {shares}股 均价{avg_buy} | 盈亏 {pnl_pct} ({pnl_value})")
        else:
            lines.append("💼 持仓: 暂未持有")

        dip_opportunity = getattr(result, "monthly_dip_opportunity", None) or {}
        dip_entry = _safe_text(dip_opportunity.get("dip_entry_zone"))
        lines.append(f"💰 买入区间: {dip_entry}")

        catalyst_strength = _safe_text(dip_opportunity.get("catalyst_strength"))
        catalyst_summary = _safe_text(dip_opportunity.get("catalyst_summary"))
        lines.append(f"📰 催化剂: {catalyst_strength} — {catalyst_summary}")

        if tier == 2:
            trim_target = _safe_text(dip_opportunity.get("trim_target"))
            lines.append(f"🎯 止盈目标: {trim_target}")

        if is_deposit_month:
            verdict = _safe_text(dip_opportunity.get("verdict"))
            rank = getattr(result, "monthly_priority_rank", None)
            action = "⏸️ 持有观望"
            if rank == 1:
                action = "✅ 优先买入"
            elif rank == 2:
                action = "🥈 次选"
            elif verdict == "本月跳过":
                action = "❌ 本月跳过"
            lines.append(f"🎯 本月操作: {action}")


        if budget_suggestion:
            deploy_text = _format_money(budget_suggestion.get("deploy_amount"))
            total_text = _format_money(budget_suggestion.get("total_budget"))
            remaining_text = _format_money(budget_suggestion.get("remaining_after"))
            lines.append(
                f"Suggested deploy: {deploy_text} of your {total_text}. Remaining after this: {remaining_text}"
            )
        return self._send("\n".join(lines))

    def send_monthly_summary(self, ranked_results: List, portfolio: Dict) -> bool:
        _ = portfolio
        if not ranked_results:
            return self._send("💰 *本月资金部署建议*\n\n暂无可用分析结果")

        sorted_results = sorted(
            ranked_results,
            key=lambda r: getattr(r, "monthly_priority_rank", 99) if r is not None else 99,
        )

        top1 = sorted_results[0] if len(sorted_results) > 0 else None
        top2 = sorted_results[1] if len(sorted_results) > 1 else None

        def entry_zone(result) -> str:
            info = getattr(result, "monthly_dip_opportunity", None) or {}
            return _safe_text(info.get("dip_entry_zone"))

        hold_watch = []
        skip = []
        for result in sorted_results:
            info = getattr(result, "monthly_dip_opportunity", None) or {}
            verdict = info.get("verdict")
            if verdict == "本月跳过":
                skip.append(result.code)
            elif result not in (top1, top2):
                hold_watch.append(result.code)

        lines = ["💰 *本月资金部署建议*", ""]
        if top1:
            lines.append(f"🥇 优先: {top1.code} — 区间 {entry_zone(top1)}")
        if top2:
            lines.append(f"🥈 次选: {top2.code} — 区间 {entry_zone(top2)}")
        lines.append(f"⏸️ 持有观望: {', '.join(hold_watch) if hold_watch else '暂无'}")
        lines.append(f"❌ 本月跳过: {', '.join(skip) if skip else '暂无'}")

        return self._send("\n".join(lines))
