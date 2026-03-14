# US Stock Analyzer

US stock analysis pipeline powered by Gemini, with Telegram delivery.

This fork is intentionally streamlined and focused on US stocks. It supports:

- US stocks + US market review only
- Gemini as the LLM provider
- Telegram as the notification channel
- Local runs or scheduled GitHub Actions runs
- Optional signal filtering, portfolio-aware market review, bot listener, and earnings evaluator

---

## What It Does

- Analyzes a configurable watchlist of US tickers (e.g., `AAPL`, `MSFT`, `NVDA`, `SPY`, `QQQ`)
- Generates a US market review
- Produces two Telegram message types:
  - **Buy Alerts** for confluence signals above a threshold
  - **Daily Digest** summary for all watchlist stocks
- Tracks monthly cash deployment and suggests per-buy allocation
- Adds a portfolio impact section to the market review (optional)
- Supports a Telegram chatbot for on-demand analysis (optional)
- Evaluates recent earnings using FMP + Gemini (optional)

---

## How It Works

Main entrypoint: `main.py`

Runtime flow (daily run):

1. Load config from `.env` or GitHub Actions secrets.
2. Resolve the correct US trading session for your configured timezone.
3. Fetch recent price data + ~1 year of history for each ticker.
4. Enrich with fundamentals, 52-week range, relative strength vs `SPY`, and recent news.
5. Send context to Gemini via LiteLLM.
6. Parse output into structured analysis results.
7. Apply signal filtering:
   - Buy alerts for high-confluence signals
   - Daily digest summary for all stocks
8. Optional US market review (with portfolio impact section if enabled).
9. Optional earnings evaluator for recent reports.
10. Send Telegram messages.

Key modules:

- `main.py`: CLI entrypoint and orchestration
- `src/core/pipeline.py`: stock analysis pipeline
- `src/analyzer.py`: Gemini-based stock analysis
- `src/core/market_review.py`: US market review flow
- `src/market_analyzer.py`: market review prompt generation
- `src/notification.py`: report building and Telegram delivery
- `src/core/signal_filter.py`: buy alert vs digest filtering
- `src/core/budget_tracker.py`: monthly cash allocation tracking
- `src/bot/telegram_listener.py`: Telegram polling listener (optional)
- `src/core/earnings_evaluator.py`: earnings summarization (optional)
- `data_provider/fmp_provider.py`: FMP financial data (optional)

---

## Analysis Basis

The analysis combines:

- Historical and recent market data from the data provider layer
- Realtime quote augmentation when available
- Technical context (trend, moving averages, confluence signals)
- Fundamental context (valuation, growth, leverage, 52-week range)
- Recent news from multiple providers
- Gemini prompt synthesis and structured output parsing

This is an AI-assisted analysis tool, not an execution system and not financial advice.

---

## Configuration

The supported configuration lives in `.env.example`.

**Required for normal use:**

- `STOCK_LIST`
- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

**Signal filtering:**

- `BUY_ALERT_MIN_SCORE=70`
- `BUY_ALERT_ENABLED=true`
- `DAILY_DIGEST_ENABLED=true`

**Monthly cash allocation (optional):**

- `MONTHLY_BUDGET=400`
- `MONTHLY_DEPOSIT_DATE=1`

**Portfolio-aware market review (optional):**

- `PORTFOLIO_IMPACT_ENABLED=true`

**Telegram bot listener (optional):**

- `BOT_LISTENER_ENABLED=true`
- `BOT_LISTENER_POLL_INTERVAL=5`
- `CONCENTRATION_WARN_THRESHOLD=60`

**Earnings evaluator (optional):**

- `EARNINGS_EVAL_ENABLED=true`
- `FMP_API_KEY=your_key_here`
- `EARNINGS_LOOKBACK_DAYS=7`

**Useful optional settings:**

- `TAVILY_API_KEYS`, `SERPAPI_API_KEYS`, `BRAVE_API_KEYS`, `BOCHA_API_KEYS`
- `MARKET_REVIEW_ENABLED`
- `TRADING_DAY_CHECK_ENABLED`
- `ANALYSIS_DELAY`
- `TIMEZONE`
- `SCHEDULE_TIME`
- `POST_MARKET_DELAY`
- `HISTORICAL_LOOKBACK_DAYS`

---

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
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id
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

---

## Telegram Output

- **Buy Alert**: sent only when a stock meets the confluence threshold
- **Daily Digest**: sent as a single summary message for all watchlist stocks
- **Market Review**: optional, can include a Portfolio Impact section
- **Earnings Report**: optional, sent for recent earnings events

---

## GitHub Actions

Scheduled workflow: `.github/workflows/daily_analysis.yml`
Bot listener workflow (hourly keepalive): `.github/workflows/bot_listener.yml`

Set these secrets:

- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `STOCK_LIST`
- `TAVILY_API_KEYS` (optional for news enrichment)

---

## Artifacts

Local outputs:

- `reports/`
- `logs/`
- `data/`

---

## Project Structure

```text
.
|-- main.py
|-- src/
|   |-- analyzer.py
|   |-- market_analyzer.py
|   |-- notification.py
|   |-- bot/telegram_listener.py
|   `-- core/
|       |-- pipeline.py
|       |-- signal_filter.py
|       |-- budget_tracker.py
|       `-- earnings_evaluator.py
|-- data_provider/
|   `-- fmp_provider.py
|-- reports/
|-- logs/
`-- .github/workflows/
```

---

## Scope

This README reflects the supported runtime path of this fork.

Out of scope for this version:

- China A-share analysis
- Hong Kong stock analysis
- Email or non-Telegram channels
- Multi-market scheduling or region switching beyond `us`

Some legacy files may reference upstream features not supported here. Use this README and `.env.example` as the source of truth.

---

## Development

Basic validation commands:

```bash
python -m py_compile main.py src/*.py data_provider/*.py
flake8 main.py src/ --max-line-length=120
```

Changelog:

- `docs/CHANGELOG.md`

---

## Disclaimer

This project is for research and workflow automation only. It does not constitute investment advice. You are responsible for validating any output before making trading decisions.
