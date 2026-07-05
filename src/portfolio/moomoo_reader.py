"""
Read-only Moomoo portfolio reader.

Connects to a locally-running OpenD gateway and queries current positions.
Only position/quote queries are used — no order-placement APIs are imported
and no trade unlock is performed, so this module cannot place trades.
"""

import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)

_SECURITY_FIRM_DEFAULT = "FUTUINC"


def _build_row(code: str, qty: float, cost_price, nominal_price, market_val, pl_val) -> Dict:
    ticker = code.split(".", 1)[-1].upper() if "." in code else code.upper()
    return {
        "ticker": ticker,
        "shares": qty,
        "avg_buy_price": cost_price,
        "current_price": nominal_price,
        "total_value": market_val,
        "pnl": pl_val,
    }


class MoomooPortfolioReader:
    """Fetches current US positions from Moomoo via a local OpenD gateway."""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        security_firm: str = None,
        trd_env: str = None,
    ):
        self._host = host or os.getenv("MOOMOO_HOST", "127.0.0.1")
        self._port = int(port or os.getenv("MOOMOO_PORT", "11111"))
        self._security_firm_name = security_firm or os.getenv("MOOMOO_SECURITY_FIRM", _SECURITY_FIRM_DEFAULT)
        self._trd_env_name = trd_env or os.getenv("MOOMOO_TRD_ENV", "REAL")

    def get_positions(self) -> Dict[str, Dict]:
        """Return positions keyed by ticker, matching the portfolio sheet schema.

        Returns an empty dict on any connection/query failure — callers must
        treat an empty result as "unavailable", not "zero holdings".
        """
        try:
            from moomoo import OpenSecTradeContext, TrdMarket, SecurityFirm, TrdEnv, RET_OK
        except ImportError:
            logger.error("moomoo-api is not installed; run `pip install -r requirements-local.txt`")
            return {}

        security_firm = getattr(SecurityFirm, self._security_firm_name, SecurityFirm.FUTUINC)
        trd_env = getattr(TrdEnv, self._trd_env_name, TrdEnv.REAL)

        ctx = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.US,
            host=self._host,
            port=self._port,
            security_firm=security_firm,
        )
        try:
            ret, data = ctx.position_list_query(trd_env=trd_env)
            if ret != RET_OK:
                logger.error("Moomoo position_list_query failed: %s", data)
                return {}

            positions: Dict[str, Dict] = {}
            for _, row in data.iterrows():
                qty = float(row.get("qty", 0) or 0)
                if qty == 0:
                    continue
                position = _build_row(
                    code=str(row.get("code", "")),
                    qty=qty,
                    cost_price=row.get("cost_price"),
                    nominal_price=row.get("nominal_price"),
                    market_val=row.get("market_val"),
                    pl_val=row.get("pl_val"),
                )
                positions[position["ticker"]] = position

            total_value = sum(p["total_value"] or 0 for p in positions.values())
            for position in positions.values():
                position["allocation_pct"] = (
                    round(position["total_value"] / total_value * 100, 2) if total_value else None
                )

            return positions
        finally:
            ctx.close()


def get_moomoo_positions() -> Dict[str, Dict]:
    """Convenience entry point mirroring load_portfolio_from_config()'s return shape."""
    return MoomooPortfolioReader().get_positions()
