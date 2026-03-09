# US Stock Analyzer

US stock analysis pipeline powered by Gemini, with daily report delivery by email.

This fork is intentionally streamlined. The supported path is:

- US stocks and US market review only
- Gemini as the LLM provider
- Email as the notification channel
- Local runs or scheduled GitHub Actions runs

It is designed for a simple workflow: define a US watchlist, fetch market data, enrich with recent news, generate AI analysis, and send a report by email.

## What It Does

- Analyzes a configurable list of US tickers such as `AAPL`, `MSFT`, `NVDA`, `SPY`, and `QQQ`
- Generates a US market review for major US indices
- Uses Gemini to turn technical, fundamental, macro, and news context into a readable long-term investing report
- Sends the final report by email
- Skips non-trading days by default using US market calendar checks
- Supports local execution and GitHub Actions scheduling

## How It Works

The main entrypoint is [main.py](main.py).

Runtime flow:

1. Load config from `.env` or GitHub Actions secrets.
2. Resolve the correct US trading session for post-close delivery in your configured timezone.
3. Fetch recent price data plus roughly one year of history for each ticker.
4. Enrich the context with fundamentals, 52-week range, relative strength vs `SPY`, and merged news from multiple providers.
5. Send the assembled context to Gemini through LiteLLM.
6. Parse the model output into structured stock analysis results.
7. Generate a stock report and optional US market review.
8. Send the final report by email.

Key modules:

- [main.py](main.py): CLI entrypoint and orchestration
- [src/core/pipeline.py](src/core/pipeline.py): stock analysis pipeline
- [src/analyzer.py](src/analyzer.py): Gemini-based stock analysis
- [src/core/market_review.py](src/core/market_review.py): US market review flow
- [src/market_analyzer.py](src/market_analyzer.py): market review generation
- [src/notification.py](src/notification.py): email-only report delivery
- [src/core/trading_calendar.py](src/core/trading_calendar.py): US trading-day checks

## Analysis Basis

The analysis is based on a combination of:

- Historical and recent market data from the project data provider layer
- Realtime quote augmentation when available
- Technical context such as price trend and moving-average structure
- Fundamental context such as valuation, growth, leverage, and 52-week range
- Recent news and search results merged across multiple providers, including Yahoo Finance RSS
- Gemini prompt synthesis and structured output parsing

This is an AI-assisted analysis tool, not an execution system and not financial advice.

## Supported Configuration

The current supported configuration is the minimal setup in [.env.example](.env.example).

Required for normal use:

- `STOCK_LIST`
- `GEMINI_API_KEY`
- `EMAIL_SENDER`
- `EMAIL_PASSWORD`
- `EMAIL_RECEIVERS`

Useful optional settings:

- `TAVILY_API_KEYS`
- `SERPAPI_API_KEYS`
- `BRAVE_API_KEYS`
- `BOCHA_API_KEYS`
- `MARKET_REVIEW_ENABLED`
- `MERGE_EMAIL_NOTIFICATION`
- `TRADING_DAY_CHECK_ENABLED`
- `TIMEZONE`
- `SCHEDULE_TIME`
- `POST_MARKET_DELAY`
- `HISTORICAL_LOOKBACK_DAYS`

Important defaults:

- `MARKET_REVIEW_REGION=us`
- `MERGE_EMAIL_NOTIFICATION=true`
- `SINGLE_STOCK_NOTIFY=false`
- `TIMEZONE=Asia/Kuala_Lumpur`
- `SCHEDULE_TIME=08:00`
- `NEWS_MAX_AGE_DAYS=7`
- `HISTORICAL_LOOKBACK_DAYS=252`

## Quick Start

### Local Run

```bash
git clone <your-fork-url>
cd daily_stock_analysis
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set at least:

```env
STOCK_LIST=AAPL,MSFT,NVDA,SPY,QQQ
GEMINI_API_KEY=your_key
EMAIL_SENDER=your_email@example.com
EMAIL_PASSWORD=your_smtp_app_password
EMAIL_RECEIVERS=you@example.com
EMAIL_SENDER_NAME=US Stock Analyzer
```

Run:

```bash
python main.py
```

Useful commands:

```bash
python main.py --stocks AAPL,MSFT,NVDA
python main.py --market-review
python main.py --no-market-review
python main.py --dry-run
python main.py --force-run
```

## GitHub Actions Setup

The scheduled workflow is [daily_analysis.yml](.github/workflows/daily_analysis.yml).

It currently runs:

- On weekdays at `22:30 UTC`
- Manually through `workflow_dispatch`
- In one of three modes: `full`, `market-only`, or `stocks-only`

Set these repository secrets:

- `GEMINI_API_KEY`
- `EMAIL_SENDER`
- `EMAIL_PASSWORD`
- `EMAIL_RECEIVERS`
- `EMAIL_SENDER_NAME`
- `STOCK_LIST`
- `TAVILY_API_KEYS` if you want news enrichment

Recommended `STOCK_LIST` example:

```text
AAPL,MSFT,NVDA,SPY,QQQ
```

## Output

The project generates local artifacts under:

- `reports/`
- `logs/`
- `data/`

Depending on your settings, the email can contain:

- Stock analysis only
- US market review only
- A merged stock + market review email

## Project Structure

```text
.
|-- main.py
|-- src/
|   |-- analyzer.py
|   |-- market_analyzer.py
|   |-- notification.py
|   `-- core/
|-- data_provider/
|-- reports/
|-- logs/
`-- .github/workflows/
```

## Current Scope

This README reflects the current supported runtime path of this fork.

Out of scope for this version:

- China A-share analysis
- Hong Kong stock analysis
- WeChat, Feishu, Telegram, Discord, PushPlus, Pushover, and other non-email delivery channels
- Multi-market scheduling or region switching beyond `us`

Some inherited files and historical docs may still reference upstream features that are no longer part of the supported flow. Use this README, [.env.example](.env.example), and [daily_analysis.yml](.github/workflows/daily_analysis.yml) as the source of truth for current usage.

## Development

Basic validation commands:

```bash
python -m py_compile main.py src/*.py data_provider/*.py
flake8 main.py src/ --max-line-length=120
```

Project changelog:

- [docs/CHANGELOG.md](docs/CHANGELOG.md)

## Disclaimer

This project is for research and workflow automation only. It does not constitute investment advice. You are responsible for validating any output before making trading decisions.
