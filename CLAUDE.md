# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run market review (main entry point)
python main.py

# Common flags
python main.py --force-run          # ignore trading day check
python main.py --no-notify          # run but skip Telegram send
python main.py --debug              # verbose logging
python main.py --no-market-review   # skip market review entirely

# Tests
pytest tests/ -v
pytest tests/test_config_validate_structured.py  # single file
pytest tests/ -k "test_name"                     # single test by name

# Install dependencies
pip install -r requirements.txt
```

## Architecture

This is a **daily automated US market review system** that fetches market data, aggregates news, runs Gemini AI analysis, and delivers a structured report to Telegram. It also runs a light Telegram bot for portfolio snapshots, and a daily news digest.

> **On-demand single-stock analysis (`analyze TICKER`) lives in a separate repo** — `stock_analyzer_bot` — with its own Telegram bot token. The heavy analysis pipeline (technical indicators, signal filtering, budget tracking, SQLite storage) was extracted there. This repo no longer contains it.

### Entry Point and Flow

`main.py` → `src/core/market_review.py:run_market_review()` is the critical path:

1. Load config singleton (`src/config.py:get_config()`)
2. Check trading calendar (`src/core/trading_calendar.py`) — skips non-US trading days unless `--force-run`
3. `MarketAnalyzer` (`src/market_analyzer.py`) fetches US index data (SPY, QQQ, DJI, VIX, Gold) via `data_provider/`
4. `SearchService` (`src/search_service.py`) aggregates news from Tavily/SerpAPI/Brave/Finnhub with automatic key rotation
5. `GeminiAnalyzer` (`src/analyzer.py`) sends data to Gemini via LiteLLM and parses the structured JSON response
6. Portfolio P&L loaded from Google Sheets (`src/portfolio/google_sheets_reader.py`) and appended to report
7. `NotificationService` (`src/notification.py`) + `TelegramSender` (`src/notification_sender/telegram_sender.py`) delivers HTML-formatted message

### Key Modules

| Module | Role |
|--------|------|
| `src/config.py` | Singleton dataclass config; reads `.env`; validates required keys |
| `src/analyzer.py` | LiteLLM wrapper for Gemini; handles fallback model, JSON repair, token counting |
| `src/market_analyzer.py` | Builds the 4-section market review; fetches 11 SPDR sector ETFs for 板块轮动 |
| `src/core/market_profile.py` | `US_PROFILE` / `CN_PROFILE` — controls which sections are enabled per region |
| `src/search_service.py` | Multi-provider news search; auto-rotates API keys; deduplicates results |
| `data_provider/base.py` | Strategy pattern fetcher manager; yfinance is the primary provider |
| `src/core/daily_news.py` | Daily news digest; sends links + affected-ticker tags via `send_news_digest()` |
| `src/core/earnings_evaluator.py` | FMP earnings data → Gemini evaluation; gated by `EARNINGS_EVAL_ENABLED`; invoked from `market_review.py` |
| `src/bot/telegram_listener.py` | Hourly-polled Telegram bot for `portfolio` + `help` commands |
| `src/core/value_radar.py` | Deterministic (no LLM) quality-at-fair-price scan; appended as a 💎 section to the review; gated by `VALUE_RADAR_ENABLED` |
| `src/portfolio/moomoo_reader.py` | Read-only Moomoo position reader (local OpenD only); used by `scripts/sync_moomoo_portfolio.py`, never by CI |

### Scheduling

All production runs are via GitHub Actions, not a local scheduler:

- `daily_analysis.yml` — cron 22:00 UTC (08:00 MYT), runs after US market close
- `bot_listener.yml` — cron every hour for Telegram bot polling
- `daily_news.yml` — daily news aggregation

Secrets (API keys, tokens) live in GitHub Actions secrets, not committed files.

### Configuration

Config is loaded once at startup into a frozen singleton. All modules call `get_config()` to access it. Multi-value env vars (e.g. `TAVILY_API_KEYS`) accept comma-separated values for automatic key rotation.

Runtime state files (created automatically in `data/`):
- `bot_state.json` — tracks processed Telegram message IDs for the portfolio/help bot

### LLM Integration

`GeminiAnalyzer` uses LiteLLM for provider-agnostic calls. The primary model is `LITELLM_MODEL` (default: `gemini/gemini-2.5-flash`), with automatic fallback to `GEMINI_MODEL_FALLBACK`. Responses are expected as structured JSON; `json_repair` handles malformed outputs. To swap providers, change `LITELLM_MODEL` in `.env` (e.g., `openai/gpt-4o`, `anthropic/claude-3-5-sonnet`).

### Market Review Sections

The `run_daily_review()` flow in `src/market_analyzer.py` produces 4 sections:

1. **📊 指数表现** — SPY/QQQ/DJI/VIX/Gold from `_get_main_indices()`
2. **📰 重大事件** — requires `search_service` to be initialized; gated in `main.py` on any of `finnhub_api_keys`, `fmp_api_keys`, `tavily_api_keys`, `brave_api_keys`, or `serpapi_keys`
3. **🔄 板块轮动** — 11 SPDR sector ETFs (XLK, XLF, XLV, XLY, XLP, XLE, XLI, XLB, XLU, XLRE, XLC) fetched in `_get_us_sector_rankings()` via yfinance; sorted by today's `change_pct`
4. **⚠️ 明日关注** — LLM inference from indices + news context

### Portfolio Snapshot

`send_portfolio_snapshot()` in `telegram_sender.py` shows **今日盈亏** (today's live P&L) — computed as `sum(position_value × today_change%)` across all holdings, so it always reconciles with the per-stock contributions shown below it. Requires each portfolio row to have `total_value` (or `shares` + `current_price`).

### Daily News Digest

`src/core/daily_news.py:run_daily_news()` sends via `send_news_digest()` (HTML parse mode) so `[title](url)` links render as clickable anchors in Telegram. Each headline also shows `(涉及: NVDA, MU)` from either the LLM's `affected_tickers` field or a regex keyword scan against `STOCK_LIST` + portfolio tickers.

### Moomoo Portfolio Sync (local only, read-only)

The portfolio Google Sheet can be kept in sync with real Moomoo holdings instead of manual entry. This is intentionally **local-only and read-only** — no trading, ever:

- `src/portfolio/moomoo_reader.py` connects to a locally-running **OpenD** gateway (free download from moomoo) via the `moomoo-api` package and calls `position_list_query()` only. No order-placement API is imported and no trade unlock is performed, so the integration cannot place trades.
- `scripts/sync_moomoo_portfolio.py` reads positions and overwrites the Google Sheet's `Portfolio` tab with the exact schema `GoogleSheetsReader` expects (`ticker, shares, avg_buy_price, current_price, total_value, pnl, allocation_pct`). If Moomoo returns zero positions or errors, the sheet is left untouched (never wipes good data with an empty sync).
- `moomoo-api` lives in `requirements-local.txt`, not `requirements.txt` — GitHub Actions never installs it; the sync only runs on the user's own machine (Task Scheduler, twice daily, plus on-demand via `scripts/sync_moomoo.bat`).
- Env vars (local `.env` only): `MOOMOO_HOST` (default `127.0.0.1`), `MOOMOO_PORT` (default `11111`), `MOOMOO_SECURITY_FIRM` (default `FUTUINC`), `MOOMOO_TRD_ENV` (default `REAL`).
- Everything downstream (`market_review.py`, `telegram_listener.py`, `daily_news.py`) is unchanged — it still reads the same sheet via `load_portfolio_from_config()`.

### Value Radar (💎 价值雷达)

`src/core/value_radar.py` is a deterministic, rules-based (no LLM) scan for "great company at a fair price" — the user's long-term compounding filter. It runs in CI as part of the normal daily review, gated by `VALUE_RADAR_ENABLED` (default true):

- **Quality gates** (must all pass): ROE, gross/operating margin, revenue growth, debt/equity, positive free cash flow — sourced from `yfinance_fetcher.get_fundamentals()`. Thresholds are `VALUE_RADAR_*` env overrides.
- **Fair-price triggers** (any one): ≥15% discount from 52-week high, PEG < 1.5, or PE < 25.
- **Watchlist pass** scans `STOCK_LIST`; **discovery pass** scans FMP's `/stock-screener` (large-cap US, cached 24h) for names outside the watchlist, skipped silently if no FMP key is configured.
- `build_value_radar_section()` returns a compact bullet-list Markdown string (or `""` if nothing qualifies) appended to `review_report` in `market_review.py` before it's saved/sent — length-capped so the combined Telegram message stays under ~3800 chars (`send_market_review` does not split long messages).

### Telegram Output

Each message type has its own send method with the correct parse mode:
- `send_market_review()` — HTML via `_markdown_to_html()`
- `send_news_digest()` — HTML with `[text](url)` → `<a href>` conversion
- `send_portfolio_snapshot()` — MarkdownV2
- `send_text()` — MarkdownV2 (default for other messages)
