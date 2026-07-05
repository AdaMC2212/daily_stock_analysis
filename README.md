# US Stock Analyzer

A personal US stock analysis pipeline powered by Gemini, with Telegram delivery. Built for long-term retail investors who want daily market awareness, systematic monthly deployment, and on-demand stock evaluation — all delivered to Telegram without needing to open a brokerage or news app.

---

## What It Does

The system runs on two separate flows:

**Daily automated flow (runs every morning after US market close):**
- Fetches price data, fundamentals, and news for your watchlist
- Runs AI analysis on each stock using a quality-first framework
- Sends buy alerts for high-confidence signals
- Sends a daily digest summary for all watchlist stocks
- Sends a US market review with portfolio impact
- Evaluates recent earnings reports if any watchlist stocks reported
- Sends a portfolio snapshot showing today's moves and biggest movers

**On-demand flow (triggered via Telegram bot):**
- Type `analyse TICKER` to evaluate any stock for potential purchase
- Returns a quality/growth/valuation/macro assessment
- Includes portfolio fit check — sector concentration and correlation with your existing holdings

---

## How It Works — Daily Flow

### Step 1 — Data Fetching
For each ticker in `STOCK_LIST`, the pipeline fetches:
- Up to 252 trading days of historical OHLCV data via Yahoo Finance
- Realtime quote (current price, change %, volume)
- Fundamentals: PE, Forward PE, PEG, gross margin, profit margin, ROE, debt/equity, free cash flow, revenue growth, EPS growth, 52-week range, sector/industry, analyst ratings
- Relative strength vs SPY (how this stock has performed vs the benchmark)
- News from up to 5 parallel searches across Tavily/Brave/SerpAPI covering: latest news, risk factors, earnings expectations, analyst reports, industry outlook

### Step 2 — Technical Analysis
The `StockTrendAnalyzer` computes:
- MA5/MA10/MA20/MA60 alignment and trend status (Strong Bull → Strong Bear)
- Bias rate: how far price has deviated from MA5 (>5% above = do not chase)
- Volume analysis: shrinking volume on pullback = healthy consolidation signal
- MACD (12/26/9): golden cross above zero axis = strongest buy signal
- RSI (6/12/24): overbought >70, oversold <30
- Support/resistance levels based on MA proximity
- A signal score (0–100) combining all of the above

### Step 3 — AI Analysis (Quality-First Framework)
All data is assembled and sent to Gemini. The AI evaluates each stock across four dimensions in priority order:

**1. Quality (most important)**
Gross margin >40% indicates pricing power. ROE >15% indicates capital efficiency. Positive free cash flow means the business genuinely makes money. Debt/equity <1.5 means the company can survive rate hikes. The core question: can this company survive and stay profitable in a downturn?

**2. Growth**
Revenue growth >15% YoY is strong, 5–15% is acceptable, <5% needs a clear reason. EPS growth trend — accelerating or decelerating? Forward EPS estimates — are analysts raising or cutting? The core question: will this company be worth more in 3 years?

**3. Valuation Relative to Growth**
PEG ratio (PE / growth rate) is used rather than raw PE. PEG <1 is cheap, 1–2 is fair, >2 is expensive. Raw PE is misleading for growth stocks. The core question: is the price paying a fair premium for the growth?

**4. Macro Fit**
Interest rate environment impact on the sector. Geopolitical or regulatory risk. Relative strength vs SPY over 6 months. The core question: are external forces working for or against this stock over the next 12 months?

The AI returns a structured JSON with `sentiment_score` (0–100), `operation_advice`, `trend_prediction`, `monthly_priority_rank`, `monthly_dip_opportunity`, and detailed analysis fields.

**Scoring reference:**
- 85–100: Strong fundamentals + price in a reasonable pullback zone → strong add
- 70–84: Good fundamentals + acceptable price → suitable for gradual accumulation
- 55–69: Average fundamentals or price too high → wait for better entry
- 40–54: Fundamentals uncertain or price elevated → observe only
- <40: Fundamentals deteriorating or valuation extreme → do not hold

### Step 4 — Monthly Deployment Ranking (Hybrid Logic)
After all stocks are analyzed, the pipeline runs a post-processing re-rank:

**Fundamental score (60% weight):** Derived from the AI's `sentiment_score`, which reflects quality + growth + valuation + macro.

**Price opportunity score (40% weight):** Based on where current price sits relative to MA20:
- Price at or below MA20 (healthy pullback): +40 points — best buying opportunity
- Price 0–3% above MA20: +30 points — still reasonable
- Price 3–8% above MA20: +15 points — slightly elevated
- Price >8% above MA20: +0 points — do not chase

The combined `opportunity_score` determines `monthly_priority_rank`. This means a fundamentally strong stock that has pulled back gets ranked higher than one that has been running up, even if the AI scored them similarly on fundamentals. Rank #1 = best quality at best current price this month.

The `monthly_dip_opportunity.verdict` is also corrected if the AI recommended immediate buying on a stock that is actually trading well above MA20 — the code overrides this to "等待回调" (wait for pullback).

### Step 5 — Signal Filtering
Results are split into two outputs:
- **Buy Alert**: only sent if `sentiment_score ≥ 70`, `decision_type = buy`, advice is Accumulate/加仓, AND the same signal triggered the previous day (consecutive day check prevents noise)
- **Daily Digest**: all watchlist stocks, one line each

### Step 6 — Budget Tracker
If `MONTHLY_BUDGET` is configured, the budget tracker manages your monthly cash deployment:
- **1st buy of the month**: deploys 45% of monthly budget → goes to rank #1 stock
- **2nd buy of the month**: deploys 30% → goes to rank #2 stock
- **3rd+ buy**: only triggers if signal scores 85+ (exceptional) → deploys remaining

This enforces systematic deployment rather than lump-sum investing.

### Step 7 — Notifications
Four message types are sent to Telegram:
1. **Buy Alert** — price, entry zone, stop loss, take profit, confidence score, trigger reasons
2. **Daily Digest** — one-line summary per stock with score and advice
3. **Market Review** — 4-section Chinese summary of market events (see below)
4. **Portfolio Snapshot** — total value, overall P&L, today's biggest movers

---

## Market Review

The daily market review runs after the stock analysis and covers:

**Section 1 — Index Performance:** SPY, QQQ, DJI closing levels and % change, plus VIX (fear gauge) and Gold (risk-off signal).

**Section 2 — Major Events:** Fed decisions, earnings reports, macro data releases, geopolitical events that actually moved the market. Maximum 5 bullet points, skipped if nothing significant happened.

**Section 3 — Sector Rotation:** Which sectors led and lagged, and why. 2–3 bullets.

**Section 4 — Watch Tomorrow:** Key risks or events to monitor. 2–3 bullets.

The review is written in Chinese in concise bullet-point format (under 300 words total) and delivered in Telegram HTML format so formatting renders correctly.

**Portfolio Snapshot** is appended after the market review showing:
- Total portfolio value and overall P&L
- Today's biggest gainers and losers from your holdings, weighted by dollar impact

**Portfolio Impact** uses live prices from your Google Sheet (which auto-updates via `GOOGLEFINANCE()` formulas), supplemented by today's `change_pct` fetched from Yahoo Finance at runtime.

---

## Earnings Evaluator

When any stock in your watchlist reports earnings within the last `EARNINGS_LOOKBACK_DAYS` days, the earnings evaluator runs automatically after the market review:

1. Fetches income statement, balance sheet, and cash flow from Financial Modeling Prep (FMP)
2. Evaluates against long-term investor criteria:
   - Gross margin: is it above 40% and improving?
   - Net profit margin: positive and growing?
   - EPS: growing YoY?
   - Current ratio: above 1.5 is healthy
   - Debt/equity: above 2.0 is concerning
   - Free cash flow: must be positive
3. Returns a structured verdict: **Strong / Decent / Weak / Concerning** with one-line commentary per metric and a 2–3 sentence long-term take

Results are cached for 24 hours to avoid redundant API calls.

---

## On-Demand Stock Analysis (`analyse TICKER`)

Triggered by typing `analyse TICKER` in Telegram. This is designed for evaluating stocks you **do not yet own** to decide if they are worth buying.

### What it evaluates

**Quality score (0–100):** ROE, gross margin, operating margin, debt/equity, free cash flow. Answers: is this a well-run business?

**Growth score (0–100):** Revenue growth YoY, EPS growth trend, Forward EPS direction, analyst rating trend. Answers: is the business compounding value?

**Macro fit:** Current rate/dollar environment impact on the sector. Structural headwinds or tailwinds. Answers: are external forces working for or against this stock?

**Portfolio fit (computed in code, not AI):**
- *Sector concentration*: checks what % of your current portfolio is already in the same sector. Flags as high concentration if adding this stock would push a sector above 40% of total holdings. Uses Yahoo Finance sector data as a fallback for tickers not in the hardcoded sector map.
- *Correlation*: fetches 60-day daily price history for the new ticker and all portfolio holdings (concurrent fetches, max 4 workers). Computes Pearson correlation. Flags any existing holding with correlation >0.75 as "highly correlated" — meaning they tend to move together, reducing diversification benefit.

### Reply format
```
🔍 TICKER — Verdict

📝 One-line core reason

📊 Quality: XX/100
   [2-3 sentence quality summary]

📈 Growth: XX/100
   [2-3 sentence growth summary]

🌍 Macro: Tailwind / Neutral / Headwind
   [1-2 sentence macro summary]

🗂 Portfolio Fit:
   [Sector concentration and correlation comment]

💰 Entry: $X–$Y | Stop: $Z

⚠️ Risks: [top 2-3 risks]

👀 Watch for: [conditions to confirm before buying]
```

---

## Telegram Bot Commands

| Command | Description |
|---|---|
| `analyse TICKER` | On-demand stock evaluation for purchase consideration |
| `portfolio` | Shows last known score and decision for all watchlist stocks |
| `help` | Lists available commands |

The bot listener runs as a separate GitHub Actions workflow (`bot_listener.yml`) on an hourly schedule, polling for new messages.

---

## Portfolio Integration (Google Sheets)

Your portfolio is read from a Google Sheet in read-only mode using a service account. The sheet must have these exact column headers:

| Column | Description |
|---|---|
| `Ticker` | Stock ticker symbol |
| `Shares` | Number of shares held |
| `avg_buy_price` | Your average cost basis |
| `current_price` | Current price (use `GOOGLEFINANCE()` formula — auto-updates) |
| `total_value` | Current total value (shares × current_price) |
| `PNL` | Dollar profit/loss |
| `allocation_pct` | % of total portfolio |

The `pnl_pct` (percentage return since purchase) is computed in code from `avg_buy_price` and `current_price` — you do not need a separate column for it.

Today's daily change % is fetched from Yahoo Finance at runtime and is not read from the sheet.

### Moomoo Auto-Sync (optional, local only)

Instead of manually maintaining the sheet, you can auto-sync your real Moomoo holdings into it. This runs entirely on your own machine and is **read-only — it cannot place trades**:

1. Install and log into [OpenD](https://www.moomoo.com/download/OpenAPI) (free), and set it to start with Windows.
2. `pip install -r requirements-local.txt` (installs `moomoo-api`, kept out of the main `requirements.txt` so CI never needs it).
3. Run `python scripts/sync_moomoo_portfolio.py` (or double-click `scripts/sync_moomoo.bat`) any time to pull current positions from OpenD and overwrite the `Portfolio` tab.
4. Optionally register the `.bat` in Windows Task Scheduler to run automatically (e.g. twice daily — after US close and again in the evening — so trades made either session are reflected before the next report).

If Moomoo returns no positions or the sync fails for any reason, the sheet is left untouched — a bad sync never wipes good data.

Config (local `.env` only, not needed in GitHub Actions):
```env
MOOMOO_HOST=127.0.0.1
MOOMOO_PORT=11111
MOOMOO_SECURITY_FIRM=FUTUINC     # confirm the right value for your account/region
MOOMOO_TRD_ENV=REAL
```

---

## Value Radar (💎 价值雷达)

A deterministic, rules-based scan for "great company at a fair price" — no AI involved, so results are reproducible and cheap to run daily. Appended as an extra section to the market review message when something qualifies; silently omitted otherwise.

**Quality gates** (a holding/candidate must pass all of these to count as a "great company"):
- ROE > 15%
- Gross margin > 40% (or operating margin > 20%)
- Revenue growth > 5%
- Debt/equity < 100
- Positive free cash flow

**Fair-price triggers** (any one qualifies as "fair price"):
- Price ≥15% below its 52-week high
- PEG ratio < 1.5
- PE ratio < 25

Two passes run each day:
- **Watchlist alerts** — checks every ticker in `STOCK_LIST` against the criteria above using Yahoo Finance fundamentals.
- **Discovery** — pulls large-cap US candidates from FMP's stock screener (cached 24h) and runs the same checks on names outside your watchlist. Skipped automatically if no FMP key is configured.

Config:
```env
VALUE_RADAR_ENABLED=true
FMP_API_KEYS=key1,key2          # enables the discovery pass; watchlist alerts work without it
# Optional threshold overrides:
VALUE_RADAR_MIN_ROE=15
VALUE_RADAR_MIN_MARGIN=40
VALUE_RADAR_MIN_OPERATING_MARGIN=20
VALUE_RADAR_MIN_REVENUE_GROWTH=5
VALUE_RADAR_MAX_DEBT_TO_EQUITY=100
VALUE_RADAR_MIN_DISCOUNT_FROM_HIGH_PCT=15
VALUE_RADAR_MAX_PEG=1.5
VALUE_RADAR_MAX_PE=25
```

---

## Stock Tiers

Stocks in your watchlist are classified into two tiers which affects how the AI frames its advice:

**Tier 1 — Core positions** (set via `TIER1_STOCKS`): Long-term hold quality companies. The AI focuses on monthly DCA entry zones and does not recommend taking profit unless fundamentals deteriorate. Examples: VOO, QQQ, NVDA, META, GOOGL.

**Tier 2 — Cyclical positions** (set via `TIER2_STOCKS`): Stocks that benefit from buying at cycle lows and trimming at cycle highs. The AI must provide a specific `trim_target` price range. Examples: TSLA, MU, IBIT.

Any stock in `STOCK_LIST` not in either tier defaults to Tier 1 behaviour.

---

## Project Structure

```
.
├── main.py                          # Entrypoint: market review + optional scheduling
├── src/
│   ├── analyzer.py                  # GeminiAnalyzer: AI analysis via LiteLLM
│   ├── stock_analyzer.py            # StockTrendAnalyzer: MA/MACD/RSI/volume logic
│   ├── storage.py                   # DatabaseManager: SQLite for OHLCV + history
│   ├── market_analyzer.py           # MarketAnalyzer: market review prompt + report
│   ├── notification.py              # NotificationService: report building
│   ├── search_service.py            # SearchService: multi-provider news search
│   ├── config.py                    # Config: singleton env-var management
│   ├── bot/
│   │   └── telegram_listener.py     # Bot polling: analyse/portfolio/help commands
│   ├── core/
│   │   ├── pipeline.py              # StockAnalysisPipeline: orchestrates full flow
│   │   ├── market_review.py         # run_market_review(): daily market review flow
│   │   ├── signal_filter.py         # Buy alert vs digest filtering + history
│   │   ├── budget_tracker.py        # Monthly cash deployment tracker
│   │   ├── earnings_evaluator.py    # Earnings report evaluation via FMP + Gemini
│   │   ├── value_radar.py           # 💎 Quality-at-fair-price scan (watchlist + FMP discovery)
│   │   ├── sector_map.py            # Sector classification with yfinance fallback
│   │   └── trading_calendar.py      # US trading day resolution
│   ├── portfolio/
│   │   ├── google_sheets_reader.py  # Read-only Google Sheets portfolio reader
│   │   └── moomoo_reader.py         # Read-only Moomoo OpenD position reader (local only)
│   └── notification_sender/
│       └── telegram_sender.py       # Telegram Bot API: all message formatting
├── data_provider/
│   ├── base.py                      # BaseFetcher + DataFetcherManager
│   ├── yfinance_fetcher.py          # Yahoo Finance: price, fundamentals, realtime
│   └── fmp_provider.py              # FMP: income statement, balance sheet, cash flow, screener
├── scripts/
│   ├── sync_moomoo_portfolio.py     # Local sync: Moomoo positions → Google Sheet
│   └── sync_moomoo.bat              # Windows Task Scheduler wrapper for the sync
├── reports/                         # Local saved reports (Markdown)
├── logs/                            # Runtime logs
├── data/                            # SQLite DB, budget state, signal history, FMP cache
└── .github/workflows/
    ├── daily_analysis.yml           # Scheduled daily run
    └── bot_listener.yml             # Hourly bot polling keepalive
```

---

## Configuration Reference

### Required

```env
STOCK_LIST=AAPL,MSFT,NVDA,SPY,QQQ    # Tickers to analyze daily
GEMINI_API_KEY=your_key               # Gemini AI (via LiteLLM)
TELEGRAM_BOT_TOKEN=your_token         # From @BotFather
TELEGRAM_CHAT_ID=your_chat_id         # Your Telegram chat ID
```

### Stock Classification

```env
TIER1_STOCKS=VOO,QQQ,NVDA,META,GOOGL  # Core long-term holds (no trim target)
TIER2_STOCKS=TSLA,MU,IBIT             # Cyclical (AI provides trim targets)
```

### Monthly Deposit

```env
MONTHLY_BUDGET=400           # Total monthly cash to deploy (your currency)
MONTHLY_DEPOSIT_DATE=1       # Day of month your salary/deposit arrives
```

### Portfolio (Google Sheets)

```env
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}   # Service account JSON
GOOGLE_SHEET_ID=your_sheet_id_from_url
GOOGLE_SHEET_TAB=Portfolio                               # Tab name in your sheet
```

### Signal Filtering

```env
BUY_ALERT_MIN_SCORE=70       # Minimum score to trigger a buy alert
BUY_ALERT_ENABLED=true
DAILY_DIGEST_ENABLED=true
```

### Market Review

```env
MARKET_REVIEW_ENABLED=true
PORTFOLIO_IMPACT_ENABLED=true   # Include portfolio snapshot in market review
```

### Earnings Evaluator

```env
EARNINGS_EVAL_ENABLED=true
FMP_API_KEY=your_fmp_key
EARNINGS_LOOKBACK_DAYS=7        # How many days back to check for earnings reports
```

### Value Radar

```env
VALUE_RADAR_ENABLED=true
FMP_API_KEYS=key1,key2          # Optional — enables the discovery pass
```
See [Value Radar](#value-radar-💎-价值雷达) above for the full threshold override list.

### Moomoo Portfolio Sync (local only)

```env
MOOMOO_HOST=127.0.0.1
MOOMOO_PORT=11111
MOOMOO_SECURITY_FIRM=FUTUINC
MOOMOO_TRD_ENV=REAL
```
Not used by GitHub Actions — only by `scripts/sync_moomoo_portfolio.py` run on your own machine.

### Telegram Bot Listener

```env
BOT_LISTENER_ENABLED=true
BOT_LISTENER_POLL_INTERVAL=5    # Seconds between polling for new messages
CONCENTRATION_WARN_THRESHOLD=60 # % sector concentration to warn about
```

### News Search (optional but recommended)

```env
TAVILY_API_KEYS=key1,key2       # Multiple keys supported, rotated automatically
SERPAPI_API_KEYS=key1
BRAVE_API_KEYS=key1
BOCHA_API_KEYS=key1
NEWS_MAX_AGE_DAYS=30
```

### Runtime

```env
TIMEZONE=Asia/Kuala_Lumpur      # Your local timezone
SCHEDULE_TIME=08:00             # When to run (local time, after US market close)
SCHEDULE_ENABLED=true
SCHEDULE_RUN_IMMEDIATELY=true   # Also run once on startup
POST_MARKET_DELAY=30            # Minutes to wait after market close before fetching
HISTORICAL_LOOKBACK_DAYS=252    # ~1 year of price history
MAX_WORKERS=3                   # Concurrent stock analysis threads
ANALYSIS_DELAY=0                # Seconds between individual stock analyses
TRADING_DAY_CHECK_ENABLED=true  # Skip non-trading days automatically
LOG_LEVEL=INFO
```

---

## Quick Start

### Local Run

```bash
git clone <your-fork-url>
cd daily_stock_analysis
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your keys
python main.py
```

### Useful CLI Flags

```bash
python main.py --market-review      # Run market review only
python main.py --no-market-review   # Skip market review
python main.py --no-notify          # Run analysis but don't send Telegram messages
python main.py --force-run          # Run even if market is closed today
python main.py --debug              # Enable debug logging
```

### GitHub Actions Setup

Set these as repository secrets:

```
GEMINI_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
STOCK_LIST
GOOGLE_CREDENTIALS_JSON
GOOGLE_SHEET_ID
TIER1_STOCKS
TIER2_STOCKS
MONTHLY_BUDGET
FMP_API_KEY           (optional, for earnings + value radar discovery)
TAVILY_API_KEYS       (optional, for news)
VALUE_RADAR_ENABLED   (optional, defaults to true)
```

The `daily_analysis.yml` workflow runs on a cron schedule. The `bot_listener.yml` workflow runs hourly to keep the Telegram bot responsive.

---

## Key Design Decisions

**Why separate quality scoring from price timing?** A great company at a high price is not a great buy. The system evaluates fundamentals and price opportunity independently, then combines them for the monthly ranking. This prevents momentum from masquerading as quality.

**Why consecutive-day check for buy alerts?** A single-day signal is often noise — news-driven, algorithm-driven, or a data anomaly. Requiring the same signal on two consecutive days filters out most false positives.

**Why Chinese output from the AI?** The AI is instructed to output analysis in Chinese to save tokens. Shorter outputs mean lower API costs and faster responses. JSON keys remain in English for code compatibility.

**Why not use the AI for portfolio fit?** Sector concentration and correlation are computed in Python code, not by the AI. This makes them deterministic, consistent, and verifiable — the AI would produce different numbers each time for the same input.

**Why Google Sheets for portfolio?** The `GOOGLEFINANCE()` formula auto-updates prices in real time. This means your portfolio data is always fresh without any additional API calls or manual updates.

---

## Telegram Message Formatting

All messages use HTML parse mode (`parse_mode="HTML"`). Bold text uses `<b>`, italic uses `<i>`. Plain bullet points use `•` (not Markdown `-`). Tables are not used in Telegram messages as they do not render — data is presented in structured plain text lines instead.

---

## Disclaimer

This project is for personal research and workflow automation only. It does not constitute investment advice. All AI-generated analysis reflects the model's interpretation of available data and may be incorrect. You are responsible for validating any output before making trading decisions.