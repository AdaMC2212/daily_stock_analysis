# -*- coding: utf-8 -*-
"""
===================================
股票智能分析系统 - 大盘复盘模块（US-only）
===================================

职责：
1. 根据 MARKET_REVIEW_REGION 配置选择市场区域（us）
2. 执行大盘复盘分析并生成复盘报告
3. 保存和发送复盘报告
"""

import logging
import os
from datetime import datetime
from typing import Optional

from src.config import get_config
from src.notification import NotificationService
from src.market_analyzer import MarketAnalyzer
from src.search_service import SearchService
from src.analyzer import GeminiAnalyzer


logger = logging.getLogger(__name__)


def run_market_review(
    notifier: NotificationService,
    analyzer: Optional[GeminiAnalyzer] = None,
    search_service: Optional[SearchService] = None,
    send_notification: bool = True,
    override_region: Optional[str] = None,
) -> Optional[str]:
    """
    执行大盘复盘分析

    Args:
        notifier: 通知服务
        analyzer: AI分析器（可选）
        search_service: 搜索服务（可选）
        send_notification: 是否发送通知
        override_region: 覆盖 config 的 market_review_region（Issue #373 交易日过滤后有效子集）

    Returns:
        复盘报告文本
    """
    logger.info("开始执行大盘复盘分析...")
    config = get_config()
    region = (
        override_region
        if override_region is not None
        else (getattr(config, 'market_review_region', 'us') or 'us')
    )
    if region != 'us':
        region = 'us'

    try:
        def _parse_bool(value: Optional[str], default: bool = True) -> bool:
            if value is None:
                return default
            v = value.strip().lower()
            if not v:
                return default
            return v not in {"0", "false", "no", "off"}

        portfolio_impact_enabled = _parse_bool(
            os.getenv("PORTFOLIO_IMPACT_ENABLED", "true"),
            default=True,
        )
        stock_list_raw = os.getenv("STOCK_LIST", "")
        stock_list = ", ".join([s.strip().upper() for s in stock_list_raw.split(",") if s.strip()])

        market_analyzer = MarketAnalyzer(
            search_service=search_service,
            analyzer=analyzer,
            region=region,
            portfolio_impact_enabled=portfolio_impact_enabled,
            portfolio_stock_list=stock_list,
        )
        review_report = market_analyzer.run_daily_review()
        
        if review_report:
            # 保存报告到文件
            date_str = datetime.now().strftime('%Y%m%d')
            report_filename = f"market_review_{date_str}.md"
            filepath = notifier.save_report_to_file(
                f"# 🎯 大盘复盘\n\n{review_report}", 
                report_filename
            )
            logger.info(f"大盘复盘报告已保存: {filepath}")
            
            # 推送通知
            if send_notification and notifier.is_available():
                # 添加标题
                report_content = f"🎯 大盘复盘\n\n{review_report}"

                success = notifier.send(
                    report_content,
                )
                if success:
                    logger.info("大盘复盘推送成功")
                else:
                    logger.warning("大盘复盘推送失败")
            elif not send_notification:
                logger.info("已跳过推送通知 (--no-notify)")
            
            return review_report
        
    except Exception as e:
        logger.error(f"大盘复盘分析失败: {e}")
    
    return None
