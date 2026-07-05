"""
Sync current Moomoo positions into the Google Sheet used as the portfolio
source for market_review.py / telegram_listener.py / daily_news.py.

Run locally (requires OpenD running) via:
    python scripts/sync_moomoo_portfolio.py

Never writes to the sheet if Moomoo returns zero positions or errors, so a
transient OpenD outage can't wipe good data.
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gspread
from google.oauth2.service_account import Credentials

from src.config import get_config
from src.portfolio.moomoo_reader import MoomooPortfolioReader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_moomoo_portfolio")

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_SHEET_HEADERS = [
    "ticker",
    "shares",
    "avg_buy_price",
    "current_price",
    "total_value",
    "pnl",
    "allocation_pct",
]


def _open_worksheet(config):
    credentials_json = config.google_credentials_json
    sheet_id = config.google_sheet_id
    tab_name = getattr(config, "google_sheet_tab", "Portfolio")
    if not credentials_json or not sheet_id:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON / GOOGLE_SHEET_ID are not configured")

    credentials_info = json.loads(credentials_json)
    credentials = Credentials.from_service_account_info(credentials_info, scopes=_SCOPES)
    client = gspread.authorize(credentials)
    sheet = client.open_by_key(sheet_id)
    return sheet.worksheet(tab_name)


def _positions_to_rows(positions: dict) -> list:
    rows = [_SHEET_HEADERS]
    for ticker in sorted(positions.keys()):
        p = positions[ticker]
        rows.append([p.get(field, "") if p.get(field) is not None else "" for field in _SHEET_HEADERS])
    return rows


def main() -> int:
    config = get_config()

    positions = MoomooPortfolioReader().get_positions()
    if not positions:
        logger.error("No positions returned from Moomoo (or OpenD unreachable) — aborting without touching the sheet.")
        return 1

    total_value = sum(p.get("total_value") or 0 for p in positions.values())
    logger.info("Fetched %d positions from Moomoo, total value %.2f", len(positions), total_value)

    try:
        worksheet = _open_worksheet(config)
        rows = _positions_to_rows(positions)
        worksheet.clear()
        worksheet.update(rows)
    except Exception as exc:
        logger.error("Failed to write positions to Google Sheet: %s", exc)
        return 1

    logger.info("Synced %d positions to the Google Sheet.", len(positions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
