# -*- coding: utf-8 -*-
"""
===================================
Stock Analysis System - Notification Layer
===================================

Responsibilities:
1. Aggregate analysis results into daily reports.
2. Support Markdown output.
3. Notification channels:
   - Telegram Bot
"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

from src.config import get_config
from src.analyzer import AnalysisResult
from bot.models import BotMessage
from src.utils.data_processing import normalize_model_used
from src.notification_sender import TelegramSender
from src.core.budget_tracker import get_budget_tracker, init_budget_tracker

logger = logging.getLogger(__name__)


class NotificationChannel(Enum):
    """通知渠道类型"""
    TELEGRAM = "telegram"


class ChannelDetector:
    """
    渠道检测器 - 简化版
    
    根据配置直接判断渠道类型（不再需要 URL 解析）
    """
    
    @staticmethod
    def get_channel_name(channel: NotificationChannel) -> str:
        """获取渠道中文名称"""
        names = {
            NotificationChannel.TELEGRAM: "Telegram",
        }
        return names.get(channel, "未知渠道")


class NotificationService:
    """
    通知服务
    
    职责：
    1. 生成 Markdown 格式的分析日报
    2. 向所有已配置的渠道推送消息（多渠道并发）
    3. 支持本地保存日报
    
    支持的渠道：
    - Telegram Bot
    
    注意：所有已配置的渠道都会收到推送
    """
    
    def __init__(self, source_message: Optional[BotMessage] = None):
        """
        初始化通知服务
        
        检测所有已配置的渠道，推送时会向所有渠道发送
        """
        config = get_config()
        self._config = config
        self._source_message = source_message
        self._budget_tracker = get_budget_tracker() or init_budget_tracker(config)

        # 仅分析结果摘要（Issue #262）：true 时只推送汇总，不含个股详情
        self._report_summary_only = getattr(config, 'report_summary_only', False)

        # Initialize channels.
        self._telegram: Optional[TelegramSender] = None
        if config.telegram_bot_token and config.telegram_chat_id:
            self._telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)
        
        # Detect all configured channels.
        self._available_channels = self._detect_all_channels()
        
        if not self._available_channels:
            logger.warning("No notification channels configured; notifications will be skipped.")
        else:
            channel_names = [ChannelDetector.get_channel_name(ch) for ch in self._available_channels]
            logger.info("Configured %s notification channel(s): %s", len(channel_names), ", ".join(channel_names))

    def _collect_models_used(self, results: List[AnalysisResult]) -> List[str]:
        models: List[str] = []
        for result in results:
            model = normalize_model_used(getattr(result, "model_used", None))
            if model:
                models.append(model)
        return list(dict.fromkeys(models))
    
    def _detect_all_channels(self) -> List[NotificationChannel]:
        """
        检测所有已配置的渠道
        
        Returns:
            已配置的渠道列表
        """
        channels: List[NotificationChannel] = []
        if self._telegram:
            channels.append(NotificationChannel.TELEGRAM)
        return channels

    def is_available(self) -> bool:
        """检查通知服务是否可用（至少有一个渠道）"""
        return len(self._available_channels) > 0
    
    def get_available_channels(self) -> List[NotificationChannel]:
        """获取所有已配置的渠道"""
        return self._available_channels
    
    def get_channel_names(self) -> str:
        """获取所有已配置渠道的名称"""
        names = [ChannelDetector.get_channel_name(ch) for ch in self._available_channels]
        return ', '.join(names)

    def generate_daily_report(
        self,
        results: List[AnalysisResult],
        report_date: Optional[str] = None
    ) -> str:
        """
        生成 Markdown 格式的日报（详细版）

        Args:
            results: 分析结果列表
            report_date: 报告日期（默认今天）

        Returns:
            Markdown 格式的日报内容
        """
        if report_date is None:
            report_date = datetime.now().strftime('%Y-%m-%d')

        # 标题
        report_lines = [
            f"# 📅 {report_date} 股票智能分析报告",
            "",
            f"> 共分析 **{len(results)}** 只股票 | 报告生成时间：{datetime.now().strftime('%H:%M:%S')}",
            "",
            "---",
            "",
        ]
        
        # 按评分排序（高分在前）
        sorted_results = sorted(
            results, 
            key=lambda x: x.sentiment_score, 
            reverse=True
        )
        
        # 统计信息 - 使用 decision_type 字段准确统计
        buy_count = sum(1 for r in results if getattr(r, 'decision_type', '') == 'buy')
        sell_count = sum(1 for r in results if getattr(r, 'decision_type', '') == 'sell')
        hold_count = sum(1 for r in results if getattr(r, 'decision_type', '') in ('hold', ''))
        avg_score = sum(r.sentiment_score for r in results) / len(results) if results else 0
        
        report_lines.extend([
            "## 📊 操作建议汇总",
            "",
            "| 指标 | 数值 |",
            "|------|------|",
            f"| 🟢 建议买入/加仓 | **{buy_count}** 只 |",
            f"| 🟡 建议持有/观望 | **{hold_count}** 只 |",
            f"| 🔴 建议减仓/卖出 | **{sell_count}** 只 |",
            f"| 📈 平均看多评分 | **{avg_score:.1f}** 分 |",
            "",
            "---",
            "",
        ])
        
        # Issue #262: summary_only 时仅输出摘要，跳过个股详情
        if self._report_summary_only:
            report_lines.extend(["## 📊 分析结果摘要", ""])
            for r in sorted_results:
                emoji = r.get_emoji()
                report_lines.append(
                    f"{emoji} **{r.name}({r.code})**: {r.operation_advice} | "
                    f"评分 {r.sentiment_score} | {r.trend_prediction}"
                )
        else:
            report_lines.extend(["## 📈 个股详细分析", ""])
            # 逐个股票的详细分析
            for result in sorted_results:
                emoji = result.get_emoji()
                confidence_stars = result.get_confidence_stars() if hasattr(result, 'get_confidence_stars') else '⭐⭐'
                
                report_lines.extend([
                    f"### {emoji} {result.name} ({result.code})",
                    "",
                    f"**操作建议：{result.operation_advice}** | **综合评分：{result.sentiment_score}分** | **趋势预测：{result.trend_prediction}** | **置信度：{confidence_stars}**",
                    "",
                ])

                self._append_market_snapshot(report_lines, result)
                
                # 核心看点
                if hasattr(result, 'key_points') and result.key_points:
                    report_lines.extend([
                        f"**🎯 核心看点**：{result.key_points}",
                        "",
                    ])
                
                # 买入/卖出理由
                if hasattr(result, 'buy_reason') and result.buy_reason:
                    report_lines.extend([
                        f"**💡 操作理由**：{result.buy_reason}",
                        "",
                    ])
                
                # 走势分析
                if hasattr(result, 'trend_analysis') and result.trend_analysis:
                    report_lines.extend([
                        "#### 📉 走势分析",
                        f"{result.trend_analysis}",
                        "",
                    ])
                
                # 短期/中期展望
                outlook_lines = []
                if hasattr(result, 'short_term_outlook') and result.short_term_outlook:
                    outlook_lines.append(f"- **短期（1-3日）**：{result.short_term_outlook}")
                if hasattr(result, 'medium_term_outlook') and result.medium_term_outlook:
                    outlook_lines.append(f"- **中期（1-2周）**：{result.medium_term_outlook}")
                if outlook_lines:
                    report_lines.extend([
                        "#### 🔮 市场展望",
                        *outlook_lines,
                        "",
                    ])
                
                # 技术面分析
                tech_lines = []
                if result.technical_analysis:
                    tech_lines.append(f"**综合**：{result.technical_analysis}")
                if hasattr(result, 'ma_analysis') and result.ma_analysis:
                    tech_lines.append(f"**均线**：{result.ma_analysis}")
                if hasattr(result, 'volume_analysis') and result.volume_analysis:
                    tech_lines.append(f"**量能**：{result.volume_analysis}")
                if hasattr(result, 'pattern_analysis') and result.pattern_analysis:
                    tech_lines.append(f"**形态**：{result.pattern_analysis}")
                if tech_lines:
                    report_lines.extend([
                        "#### 📊 技术面分析",
                        *tech_lines,
                        "",
                    ])
                
                # 基本面分析
                fund_lines = []
                if hasattr(result, 'fundamental_analysis') and result.fundamental_analysis:
                    fund_lines.append(result.fundamental_analysis)
                if hasattr(result, 'sector_position') and result.sector_position:
                    fund_lines.append(f"**板块地位**：{result.sector_position}")
                if hasattr(result, 'company_highlights') and result.company_highlights:
                    fund_lines.append(f"**公司亮点**：{result.company_highlights}")
                if fund_lines:
                    report_lines.extend([
                        "#### 🏢 基本面分析",
                        *fund_lines,
                        "",
                    ])
                
                # 消息面/情绪面
                news_lines = []
                if result.news_summary:
                    news_lines.append(f"**新闻摘要**：{result.news_summary}")
                if hasattr(result, 'market_sentiment') and result.market_sentiment:
                    news_lines.append(f"**市场情绪**：{result.market_sentiment}")
                if hasattr(result, 'hot_topics') and result.hot_topics:
                    news_lines.append(f"**相关热点**：{result.hot_topics}")
                if news_lines:
                    report_lines.extend([
                        "#### 📰 消息面/情绪面",
                        *news_lines,
                        "",
                    ])
                
                # 综合分析
                if result.analysis_summary:
                    report_lines.extend([
                        "#### 📝 综合分析",
                        result.analysis_summary,
                        "",
                    ])
                
                # 风险提示
                if hasattr(result, 'risk_warning') and result.risk_warning:
                    report_lines.extend([
                        f"⚠️ **风险提示**：{result.risk_warning}",
                        "",
                    ])
                
                # 数据来源说明
                if hasattr(result, 'search_performed') and result.search_performed:
                    report_lines.append("*🔍 已执行联网搜索*")
                if hasattr(result, 'data_sources') and result.data_sources:
                    report_lines.append(f"*📋 数据来源：{result.data_sources}*")
                
                # 错误信息（如果有）
                if not result.success and result.error_message:
                    report_lines.extend([
                        "",
                        f"❌ **分析异常**：{result.error_message[:100]}",
                    ])
                
                report_lines.extend([
                    "",
                    "---",
                    "",
                ])
        
        # 底部信息（去除免责声明）
        report_lines.extend([
            "",
            f"*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ])
        
        return "\n".join(report_lines)
    
    @staticmethod
    def _escape_md(name: str) -> str:
        """Escape markdown special characters in stock names (e.g. *ST → \\*ST)."""
        return name.replace('*', r'\*') if name else name

    @staticmethod
    def _clean_sniper_value(value: Any) -> str:
        """Normalize sniper point values and remove redundant label prefixes."""
        if value is None:
            return '暂无'
        if isinstance(value, (int, float)):
            return str(value)
        if not isinstance(value, str):
            return str(value)
        if not value or value in ('暂无', 'N/A'):
            return value
        prefixes = ['理想买入点：', '次优买入点：', '止损位：', '目标位：',
                     '理想买入点:', '次优买入点:', '止损位:', '目标位:']
        for prefix in prefixes:
            if value.startswith(prefix):
                return value[len(prefix):]
        return value

    def _get_signal_level(self, result: AnalysisResult) -> tuple:
        """
        Get signal level and color based on operation advice.

        Priority: advice string takes precedence over score.
        Score-based fallback is used only when advice doesn't match
        any known value.

        Returns:
            (signal_text, emoji, color_tag)
        """
        advice = result.operation_advice
        score = result.sentiment_score

        # Advice-first lookup (exact match takes priority)
        advice_map = {
            'Accumulate': ('Accumulate', '🟢', '加仓'),
            'Hold': ('Hold', '🟡', '持有'),
            'Watch': ('Watch', '⚪', '观察'),
            'Trim': ('Trim', '🟠', '减仓'),
            'Exit': ('Exit', '🔴', '退出'),
            '强烈买入': ('强烈买入', '💚', '强买'),
            '买入': ('买入', '🟢', '买入'),
            '加仓': ('买入', '🟢', '买入'),
            '持有': ('持有', '🟡', '持有'),
            '观望': ('观望', '⚪', '观望'),
            '减仓': ('减仓', '🟠', '减仓'),
            '卖出': ('卖出', '🔴', '卖出'),
            '强烈卖出': ('卖出', '🔴', '卖出'),
        }
        if advice in advice_map:
            signal_text, emoji, color_tag = advice_map[advice]
            english_map = {
                "Accumulate": "加仓",
                "Hold": "持有",
                "Watch": "观望",
                "Trim": "减仓",
                "Exit": "卖出",
            }
            signal_text = english_map.get(signal_text, signal_text)
            return (signal_text, emoji, color_tag)

        # Score-based fallback when advice is unrecognized
        if score >= 80:
            return ('强烈买入', '💚', '强买')
        elif score >= 65:
            return ('买入', '🟢', '买入')
        elif score >= 55:
            return ('持有', '🟡', '持有')
        elif score >= 45:
            return ('观望', '⚪', '观望')
        elif score >= 35:
            return ('减仓', '🟠', '减仓')
        elif score < 35:
            return ('卖出', '🔴', '卖出')
        else:
            return ('观望', '⚪', '观望')

    def generate_dashboard_report(
        self,
        results: List[AnalysisResult],
        report_date: Optional[str] = None
    ) -> str:
        """
        生成决策仪表盘格式的日报（详细版）

        格式：市场概览 + 重要信息 + 核心结论 + 数据透视 + 作战计划

        Args:
            results: 分析结果列表
            report_date: 报告日期（默认今天）

        Returns:
            Markdown 格式的决策仪表盘日报
        """
        if report_date is None:
            report_date = datetime.now().strftime('%Y-%m-%d')

        # 按评分排序（高分在前）
        sorted_results = sorted(results, key=lambda x: x.sentiment_score, reverse=True)

        # 统计信息 - 使用 decision_type 字段准确统计
        buy_count = sum(1 for r in results if getattr(r, 'decision_type', '') == 'buy')
        sell_count = sum(1 for r in results if getattr(r, 'decision_type', '') == 'sell')
        hold_count = sum(1 for r in results if getattr(r, 'decision_type', '') in ('hold', ''))

        report_lines = [
            f"# 🎯 {report_date} 决策仪表盘",
            "",
            f"> 共分析 **{len(results)}** 只股票 | 🟢买入:{buy_count} 🟡观望:{hold_count} 🔴卖出:{sell_count}",
            "",
        ]

        actionable_results = [
            r for r in sorted_results
            if getattr(r, 'operation_advice', '') in ('Accumulate', 'Trim', 'Exit', '买入', '加仓', '减仓', '卖出')
        ]
        if actionable_results:
            report_lines.extend([
                "## 行动关注",
                "",
            ])
            for r in actionable_results:
                _, signal_emoji, _ = self._get_signal_level(r)
                report_lines.append(
                    f"- {signal_emoji} **{self._escape_md(r.name)}({r.code})**: {r.operation_advice} | "
                    f"评分 {r.sentiment_score} | {r.analysis_summary[:90]}"
                )
            report_lines.extend(["", "---", ""])

        if results:
            report_lines.extend([
                "## 持仓评分总览",
                "",
                "| 股票 | 信号 | 评分 | 持有周期 | 核心理由 |",
                "|------|------|------|----------|----------|",
            ])
            for r in sorted_results:
                signal_text, _, _ = self._get_signal_level(r)
                reason = (r.buy_reason or r.analysis_summary or "").replace("\n", " ")[:80]
                report_lines.append(
                    f"| {r.code} | {signal_text} | {r.sentiment_score} | "
                    f"{getattr(r, 'time_horizon', '暂无')} | {reason or '暂无'} |"
                )
            report_lines.extend(["", "---", ""])

        # === 新增：分析结果摘要 (Issue #112) ===
        if results:
            report_lines.extend([
                "## 📊 分析结果摘要",
                "",
            ])
            for r in sorted_results:
                _, signal_emoji, _ = self._get_signal_level(r)
                display_name = self._escape_md(r.name)
                report_lines.append(
                    f"{signal_emoji} **{display_name}({r.code})**: {r.operation_advice} | "
                    f"评分 {r.sentiment_score} | {r.trend_prediction}"
                )
            report_lines.extend([
                "",
                "---",
                "",
            ])

        # 逐个股票的决策仪表盘（Issue #262: summary_only 时跳过详情）
        if not self._report_summary_only:
            for result in sorted_results:
                signal_text, signal_emoji, signal_tag = self._get_signal_level(result)
                dashboard = result.dashboard if hasattr(result, 'dashboard') and result.dashboard else {}
                
                # 股票名称（优先使用 dashboard 或 result 中的名称，转义 *ST 等特殊字符）
                raw_name = result.name if result.name and not result.name.startswith('股票') else f'股票{result.code}'
                stock_name = self._escape_md(raw_name)
                
                report_lines.extend([
                    f"## {signal_emoji} {stock_name} ({result.code})",
                    "",
                ])
                
                # ========== 舆情与基本面概览（放在最前面）==========
                intel = dashboard.get('intelligence', {}) if dashboard else {}
                if intel:
                    report_lines.extend([
                        "### 📰 重要信息速览",
                        "",
                    ])
                    # 舆情情绪总结
                    if intel.get('sentiment_summary'):
                        report_lines.append(f"**💭 舆情情绪**: {intel['sentiment_summary']}")
                    # 业绩预期
                    if intel.get('earnings_outlook'):
                        report_lines.append(f"**📊 业绩预期**: {intel['earnings_outlook']}")
                    # 风险警报（醒目显示）
                    risk_alerts = intel.get('risk_alerts', [])
                    if risk_alerts:
                        report_lines.append("")
                        report_lines.append("**🚨 风险警报**:")
                        for alert in risk_alerts:
                            report_lines.append(f"- {alert}")
                    # 利好催化
                    catalysts = intel.get('positive_catalysts', [])
                    if catalysts:
                        report_lines.append("")
                        report_lines.append("**✨ 利好催化**:")
                        for cat in catalysts:
                            report_lines.append(f"- {cat}")
                    # 最新消息
                    if intel.get('latest_news'):
                        report_lines.append("")
                        report_lines.append(f"**📢 最新动态**: {intel['latest_news']}")
                    report_lines.append("")
                
                # ========== 核心结论 ==========
                core = dashboard.get('core_conclusion', {}) if dashboard else {}
                one_sentence = core.get('one_sentence', result.analysis_summary)
                time_sense = core.get('time_sensitivity', '本周内')
                pos_advice = core.get('position_advice', {})
                
                report_lines.extend([
                    "### 📌 核心结论",
                    "",
                    f"**{signal_emoji} {signal_text}** | {result.trend_prediction}",
                    "",
                    f"> **一句话决策**: {one_sentence}",
                    "",
                    f"⏰ **时效性**: {time_sense}",
                    "",
                ])
                # 持仓分类建议
                if pos_advice:
                    report_lines.extend([
                        "| 持仓情况 | 操作建议 |",
                        "|---------|---------|",
                        f"| 🆕 **空仓者** | {pos_advice.get('no_position', result.operation_advice)} |",
                        f"| 💼 **持仓者** | {pos_advice.get('has_position', '继续持有')} |",
                        "",
                    ])

                self._append_market_snapshot(report_lines, result)
                
                # ========== 数据透视 ==========
                data_persp = dashboard.get('data_perspective', {}) if dashboard else {}
                if data_persp:
                    trend_data = data_persp.get('trend_status', {})
                    price_data = data_persp.get('price_position', {})
                    vol_data = data_persp.get('volume_analysis', {})
                battle = dashboard.get('battle_plan', {}) if dashboard else {}
                if battle:
                    report_lines.extend([
                        "### 🎯 作战计划",
                        "",
                    ])
                    # 狙击点位
                    sniper = battle.get('sniper_points', {})
                    if sniper:
                        report_lines.extend([
                            "**📍 狙击点位**",
                            "",
                            "| 点位类型 | 价格 |",
                            "|---------|------|",
                            f"| 🎯 理想买入点 | {self._clean_sniper_value(sniper.get('ideal_buy', '暂无'))} |",
                            f"| 🔵 次优买入点 | {self._clean_sniper_value(sniper.get('secondary_buy', '暂无'))} |",
                            f"| 🛑 止损位 | {self._clean_sniper_value(sniper.get('stop_loss', '暂无'))} |",
                            f"| 🎊 目标位 | {self._clean_sniper_value(sniper.get('take_profit', '暂无'))} |",
                            "",
                        ])
                    # 仓位策略
                    position = battle.get('position_strategy', {})
                    if position:
                        report_lines.extend([
                            f"**💰 仓位建议**: {position.get('suggested_position', '暂无')}",
                            f"- 建仓策略: {position.get('entry_plan', '暂无')}",
                            f"- 风控策略: {position.get('risk_control', '暂无')}",
                            "",
                        ])
                    # 检查清单
                    checklist = battle.get('action_checklist', []) if battle else []
                    if checklist:
                        report_lines.extend([
                            "**✅ 检查清单**",
                            "",
                        ])
                        for item in checklist:
                            report_lines.append(f"- {item}")
                        report_lines.append("")
                
                # 如果没有 dashboard，显示传统格式
                if not dashboard:
                    # 操作理由
                    if result.buy_reason:
                        report_lines.extend([
                            f"**💡 操作理由**: {result.buy_reason}",
                            "",
                        ])
                    # 风险提示
                    if result.risk_warning:
                        report_lines.extend([
                            f"**⚠️ 风险提示**: {result.risk_warning}",
                            "",
                        ])
                    # 技术面分析
                    if result.ma_analysis or result.volume_analysis:
                        report_lines.extend([
                            "### 📊 技术面",
                            "",
                        ])
                        if result.ma_analysis:
                            report_lines.append(f"**均线**: {result.ma_analysis}")
                        if result.volume_analysis:
                            report_lines.append(f"**量能**: {result.volume_analysis}")
                        report_lines.append("")
                    # 消息面
                    if result.news_summary:
                        report_lines.extend([
                            "### 📰 消息面",
                            f"{result.news_summary}",
                            "",
                        ])
                
                report_lines.extend([
                    "---",
                    "",
                ])
        
        # 底部（去除免责声明）
        report_lines.extend([
            "",
            f"*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ])
        
        return "\n".join(report_lines)

    def generate_single_stock_report(self, result: AnalysisResult) -> str:
        """
        生成单只股票的分析报告（用于单股推送模式 #55）
        
        格式精简但信息完整，适合每分析完一只股票立即推送
        
        Args:
            result: 单只股票的分析结果
            
        Returns:
            Markdown 格式的单股报告
        """
        report_date = datetime.now().strftime('%Y-%m-%d %H:%M')
        signal_text, signal_emoji, _ = self._get_signal_level(result)
        dashboard = result.dashboard if hasattr(result, 'dashboard') and result.dashboard else {}
        core = dashboard.get('core_conclusion', {}) if dashboard else {}
        battle = dashboard.get('battle_plan', {}) if dashboard else {}
        intel = dashboard.get('intelligence', {}) if dashboard else {}
        
        # 股票名称（转义 *ST 等特殊字符）
        raw_name = result.name if result.name and not result.name.startswith('股票') else f'股票{result.code}'
        stock_name = self._escape_md(raw_name)
        
        lines = [
            f"## {signal_emoji} {stock_name} ({result.code})",
            "",
            f"> {report_date} | 评分: **{result.sentiment_score}** | {result.trend_prediction}",
            "",
        ]

        self._append_market_snapshot(lines, result)
        
        # 核心决策（一句话）
        one_sentence = core.get('one_sentence', result.analysis_summary) if core else result.analysis_summary
        if one_sentence:
            lines.extend([
                "### 📌 核心结论",
                "",
                f"**{signal_text}**: {one_sentence}",
                "",
            ])
        
        # 重要信息（舆情+基本面）
        info_added = False
        if intel:
            if intel.get('earnings_outlook'):
                if not info_added:
                    lines.append("### 📰 重要信息")
                    lines.append("")
                    info_added = True
                lines.append(f"📊 **业绩预期**: {intel['earnings_outlook'][:100]}")
            
            if intel.get('sentiment_summary'):
                if not info_added:
                    lines.append("### 📰 重要信息")
                    lines.append("")
                    info_added = True
                lines.append(f"💭 **舆情情绪**: {intel['sentiment_summary'][:80]}")
            
            # 风险警报
            risks = intel.get('risk_alerts', [])
            if risks:
                if not info_added:
                    lines.append("### 📰 重要信息")
                    lines.append("")
                    info_added = True
                lines.append("")
                lines.append("🚨 **风险警报**:")
                for risk in risks[:3]:
                    lines.append(f"- {risk[:60]}")
            
            # 利好催化
            catalysts = intel.get('positive_catalysts', [])
            if catalysts:
                lines.append("")
                lines.append("✨ **利好催化**:")
                for cat in catalysts[:3]:
                    lines.append(f"- {cat[:60]}")
        
        if info_added:
            lines.append("")
        
        # 狙击点位
        sniper = battle.get('sniper_points', {}) if battle else {}
        if sniper:
            lines.extend([
                "### 🎯 操作点位",
                "",
                "| 买点 | 止损 | 目标 |",
                "|------|------|------|",
            ])
            ideal_buy = sniper.get('ideal_buy', '-')
            stop_loss = sniper.get('stop_loss', '-')
            take_profit = sniper.get('take_profit', '-')
            lines.append(f"| {ideal_buy} | {stop_loss} | {take_profit} |")
            lines.append("")
        
        # 持仓建议
        pos_advice = core.get('position_advice', {}) if core else {}
        if pos_advice:
            lines.extend([
                "### 💼 持仓建议",
                "",
                f"- 🆕 **空仓者**: {pos_advice.get('no_position', result.operation_advice)}",
                f"- 💼 **持仓者**: {pos_advice.get('has_position', '继续持有')}",
                "",
            ])
        
        lines.append("---")
        model_used = normalize_model_used(getattr(result, "model_used", None))
        if model_used:
            lines.append(f"*分析模型: {model_used}*")
        lines.append("*AI生成，仅供参考，不构成投资建议*")

        return "\n".join(lines)

    # Display name mapping for realtime data sources
    _SOURCE_DISPLAY_NAMES = {
        "fallback": "雅虎财经",
    }

    @staticmethod
    def _format_alert_price(value) -> str:
        if value is None:
            return "N/A"
        try:
            return f"${float(value):,.2f}"
        except (TypeError, ValueError):
            return "N/A"

    @staticmethod
    def _pick_digest_emoji(result: AnalysisResult) -> str:
        score = getattr(result, "sentiment_score", 0) or 0
        decision = getattr(result, "decision_type", "")
        if score >= 70 and decision == "buy":
            return "🟢"
        if score < 40 or decision == "sell":
            return "🔴"
        return "🟡"

    def build_buy_alert(self, result: AnalysisResult) -> str:
        stock_name = self._escape_md(getattr(result, "name", ""))
        code = getattr(result, "code", "")
        header = f"🚨 BUY SIGNAL — {stock_name} ({code})"

        current_price = result.current_price
        if current_price is None and result.market_snapshot:
            current_price = result.market_snapshot.get("price") or result.market_snapshot.get("close")

        sniper = result.get_sniper_points() if hasattr(result, "get_sniper_points") else {}
        ideal_buy = self._clean_sniper_value(sniper.get("ideal_buy", "N/A"))
        stop_loss = self._clean_sniper_value(sniper.get("stop_loss", "N/A"))
        take_profit = self._clean_sniper_value(sniper.get("take_profit", "N/A"))

        reasons = getattr(result, "signal_reasons", None) or []
        if reasons:
            reasons_text = "\n".join(f"- {r}" for r in reasons)
        else:
            reasons_text = "- 无"

        score = getattr(result, "sentiment_score", 0)
        advice = getattr(result, "operation_advice", "")
        summary = getattr(result, "analysis_summary", "")
        reason_line = f"{advice}: {summary}" if summary else advice

        lines = [
            header,
            "",
            f"💰 Current Price: {self._format_alert_price(current_price)}",
            f"🎯 Ideal Buy: {ideal_buy}",
            f"🛑 Stop Loss: {stop_loss}",
            f"✅ Take Profit: {take_profit}",
            f"📊 Confidence Score: {score}/100",
            "",
            "💡 Why it triggered:",
            reasons_text,
            "",
            f"📝 Summary: {reason_line}",
        ]
        return "\n".join(lines)

    def build_digest_line(self, result: AnalysisResult) -> str:
        emoji = self._pick_digest_emoji(result)
        name = self._escape_md(getattr(result, "name", ""))
        code = getattr(result, "code", "")
        advice = getattr(result, "operation_advice", "")
        score = getattr(result, "sentiment_score", "")
        trend = getattr(result, "trend_prediction", "")
        return f"{emoji} {name} ({code}): {advice} | Score: {score} | {trend}"

    def send_buy_alert(self, message: str) -> bool:
        if not self._telegram:
            logger.warning("Telegram sender is not configured.")
            return False
        return self._telegram.send_buy_alert(message)

    def send_daily_digest(self, message: str) -> bool:
        if not self._telegram:
            logger.warning("Telegram sender is not configured.")
            return False
        return self._telegram.send_daily_digest(message)


    def _append_market_snapshot(self, lines: List[str], result: AnalysisResult) -> None:
        snapshot = getattr(result, 'market_snapshot', None)
        if not snapshot:
            return

        lines.extend([
            "### 📈 当日行情",
            "",
            "| 收盘 | 昨收 | 开盘 | 最高 | 最低 | 涨跌幅 | 涨跌额 | 振幅 | 成交量 | 成交额 |",
            "|------|------|------|------|------|-------|-------|------|--------|--------|",
            f"| {snapshot.get('close', '暂无')} | {snapshot.get('prev_close', '暂无')} | "
            f"{snapshot.get('open', '暂无')} | {snapshot.get('high', '暂无')} | "
            f"{snapshot.get('low', '暂无')} | {snapshot.get('pct_chg', '暂无')} | "
            f"{snapshot.get('change_amount', '暂无')} | {snapshot.get('amplitude', '暂无')} | "
            f"{snapshot.get('volume', '暂无')} | {snapshot.get('amount', '暂无')} |",
        ])

        if "price" in snapshot:
            raw_source = snapshot.get('source', '暂无')
            display_source = self._SOURCE_DISPLAY_NAMES.get(raw_source, raw_source)
            lines.extend([
                "",
                "| 当前价 | 量比 | 换手率 | 行情来源 |",
                "|-------|------|--------|----------|",
                f"| {snapshot.get('price', '暂无')} | {snapshot.get('volume_ratio', '暂无')} | "
                f"{snapshot.get('turnover_rate', '暂无')} | {display_source} |",
            ])

        lines.append("")

    def send(
        self,
        content: str,
        results: Optional[List[AnalysisResult]] = None,
        portfolio: Optional[Dict] = None,
    ) -> bool:
        """
        统一发送接口 - 向所有已配置的渠道发送

        遍历所有已配置的渠道，逐一发送消息

        Args:
            content: 消息内容（Markdown 格式）

        Returns:
            是否至少有一个渠道发送成功
        """
        if not self._available_channels:
            logger.warning("No notification channels available; skipping.")
            return False

        telegram_result = False
        if self._telegram:
            if results is not None and portfolio is not None:
                telegram_result = self.send_via_telegram(results, portfolio)
            else:
                telegram_result = self._telegram.send_text(content)

        return telegram_result

    def send_via_telegram(self, results: List[AnalysisResult], portfolio: Dict) -> bool:
        if not self._telegram:
            logger.warning("Telegram sender is not configured.")
            return False

        is_deposit_month = datetime.now().day == self._config.monthly_deposit_date

        tier2 = set(s.upper() for s in self._config.tier2_stocks)

        def get_tier(ticker: str) -> int:
            if ticker.upper() in tier2:
                return 2
            return 1

        success = self._telegram.send_portfolio_snapshot(portfolio)
        for result in results:
            budget_suggestion = None
            if self._budget_tracker:
                is_buy_signal = getattr(result, "decision_type", "") == "buy"
                budget_suggestion = self._budget_tracker.suggest_deployment(
                    getattr(result, "sentiment_score", None),
                    is_buy_signal,
                )
            success = self._telegram.send_stock_card(
                result,
                portfolio.get(result.code.upper()),
                get_tier(result.code),
                is_deposit_month,
                budget_suggestion=budget_suggestion,
            ) and success

        if is_deposit_month:
            success = self._telegram.send_monthly_summary(results, portfolio) and success

        return success
   
    def save_report_to_file(
        self, 
        content: str, 
        filename: Optional[str] = None
    ) -> str:
        """
        保存日报到本地文件
        
        Args:
            content: 日报内容
            filename: 文件名（可选，默认按日期生成）
            
        Returns:
            保存的文件路径
        """
        from pathlib import Path
        
        if filename is None:
            date_str = datetime.now().strftime('%Y%m%d')
            filename = f"report_{date_str}.md"
        
        # 确保 reports 目录存在（使用项目根目录下的 reports）
        reports_dir = Path(__file__).parent.parent / 'reports'
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = reports_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"日报已保存到: {filepath}")
        return str(filepath)




