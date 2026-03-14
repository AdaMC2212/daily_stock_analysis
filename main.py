# -*- coding: utf-8 -*-
"""
Market-only entrypoint.

This version intentionally avoids importing or calling deleted modules
(pipeline, API server, backtest, web UI, storage-backed analysis).
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime

from src.config import get_config, setup_env
from src.logging_config import setup_logging, shutdown_logging

setup_env()

logger = logging.getLogger(__name__)


def _apply_post_market_delay(config, args: argparse.Namespace) -> None:
    delay_minutes = max(0, int(getattr(config, "post_market_delay", 0) or 0))
    if delay_minutes <= 0 or getattr(args, "force_run", False):
        return
    logger.info("Waiting %s minute(s) before fetching post-market data...", delay_minutes)
    time.sleep(delay_minutes * 60)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Market review runner (US-only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )

    parser.add_argument(
        "--market-review",
        action="store_true",
        help="Run market review (default).",
    )

    parser.add_argument(
        "--no-market-review",
        action="store_true",
        help="Skip market review and exit.",
    )

    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Do not send notifications.",
    )

    parser.add_argument(
        "--force-run",
        action="store_true",
        help="Run even when the market is closed.",
    )

    return parser.parse_args()


def run_market_review_only(config, args: argparse.Namespace) -> int:
    from src.analyzer import GeminiAnalyzer
    from src.core.market_review import run_market_review
    from src.notification import NotificationService
    from src.search_service import SearchService

    effective_region = None
    if not getattr(args, "force_run", False) and getattr(config, "trading_day_check_enabled", True):
        from src.core.trading_calendar import get_open_markets_today, compute_effective_region

        open_markets = get_open_markets_today(run_timezone=getattr(config, "timezone", "UTC"))
        effective_region = compute_effective_region(
            getattr(config, "market_review_region", "us") or "us", open_markets
        )
        if effective_region == "":
            logger.info(
                "All relevant markets are closed today; skipping. Use --force-run to override."
            )
            return 0

    notifier = NotificationService()

    search_service = None
    if config.bocha_api_keys or config.tavily_api_keys or config.brave_api_keys or config.serpapi_keys:
        search_service = SearchService(
            bocha_keys=config.bocha_api_keys,
            tavily_keys=config.tavily_api_keys,
            brave_keys=config.brave_api_keys,
            serpapi_keys=config.serpapi_keys,
            news_max_age_days=config.news_max_age_days,
        )

    analyzer = None
    if config.gemini_api_key:
        analyzer = GeminiAnalyzer(api_key=config.gemini_api_key)
        if not analyzer.is_available():
            logger.warning("Gemini analyzer is unavailable after init; check API key.")
            analyzer = None
    else:
        logger.warning("No Gemini API key detected; falling back to template report.")

    _apply_post_market_delay(config, args)

    run_market_review(
        notifier=notifier,
        analyzer=analyzer,
        search_service=search_service,
        send_notification=not args.no_notify,
        override_region=effective_region,
    )
    return 0


def main() -> int:
    args = parse_arguments()
    config = get_config()

    setup_logging(log_prefix="market_review", debug=args.debug, log_dir=config.log_dir)

    logger.info("=" * 60)
    logger.info("Market review runner started")
    logger.info("Run time: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    for warning in config.validate():
        logger.warning(warning)

    if args.no_market_review:
        logger.info("No work to run (--no-market-review).")
        return 0

    if not args.market_review and not getattr(config, "market_review_enabled", True):
        logger.info("Market review disabled by config.")
        return 0

    return run_market_review_only(config, args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutdown_logging()
