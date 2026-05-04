"""Application service for market data API endpoints."""

from __future__ import annotations

from datetime import date, timedelta

from backend.infrastructure.market_data.factory import create_fallback_market_data_provider
from backend.infrastructure.market_data.provider import MarketDataProvider
from backend.repositories import picks_repo


class MarketApiService:
    def __init__(self, market_data_provider: MarketDataProvider | None = None):
        self.market_data_provider = market_data_provider or create_fallback_market_data_provider()

    def list_stocks(self, keyword: str | None = None, limit: int = 20) -> dict:
        stocks = [item.to_dict() for item in self.market_data_provider.get_stock_list()]
        if keyword:
            normalized = keyword.strip().lower()
            stocks = [
                item
                for item in stocks
                if normalized in item["symbol"].lower() or normalized in item["name"].lower()
            ]
        return {"items": stocks[: max(1, min(limit, 200))], "total": len(stocks)}

    def get_kline(self, symbol: str, start_date: str | None = None, end_date: str | None = None, adjust: str = "qfq") -> dict:
        today = date.today()
        normalized_end = end_date or today.isoformat()
        normalized_start = start_date or (today - timedelta(days=90)).isoformat()
        bars = self.market_data_provider.get_daily_bars(symbol, normalized_start, normalized_end, adjust=adjust)
        usage = self._market_data_usage()
        return {
            "symbol": symbol,
            "start_date": normalized_start,
            "end_date": normalized_end,
            "adjust": adjust,
            "items": [bar.to_dict() for bar in bars],
            "total": len(bars),
            "provider": usage["actual_provider"],
            "market_data_source": usage["actual_provider"],
            "data_quality": usage["data_quality"],
            "fallback_used": usage["fallback_used"],
            "updated_at": date.today().isoformat(),
        }

    def get_stock_context(self, tenant_id: int, symbol: str, limit: int = 20) -> dict:
        normalized_symbol = (symbol or "").strip()
        rows = picks_repo.list_picks(
            "WHERE code=? AND COALESCE(archived,0)=0",
            [normalized_symbol],
            limit=max(1, min(int(limit or 20), 100)),
        )
        history = [self._pick_context(row, tenant_id) for row in rows]
        latest_pick = history[0] if history else None
        return {
            "tenant_id": tenant_id,
            "symbol": normalized_symbol,
            "latest_pick": latest_pick,
            "in_pool": bool(latest_pick),
            "review_markers": {
                "has_pick": bool(latest_pick),
                "status": latest_pick.get("status") if latest_pick else "",
                "review_comment": latest_pick.get("review_comment") if latest_pick else "",
                "deal_status": latest_pick.get("deal_status") if latest_pick else "",
                "watch_flag": bool(latest_pick.get("watch_flag")) if latest_pick else False,
            },
            "history": history,
            "total": len(history),
        }

    def _market_data_usage(self) -> dict:
        if hasattr(self.market_data_provider, "usage_metadata"):
            return self.market_data_provider.usage_metadata()
        health = self.market_data_provider.health_check()
        provider = health.provider or "unknown"
        return {
            "actual_provider": provider,
            "data_quality": "mock" if provider == "mock" else "primary",
            "fallback_used": False,
        }

    def _pick_context(self, row: dict, tenant_id: int) -> dict:
        return {
            "id": row.get("id"),
            "tenant_id": tenant_id,
            "symbol": row.get("code"),
            "stock_name": row.get("name"),
            "trade_date": row.get("pick_date"),
            "source": row.get("source"),
            "strategy_code": row.get("strategy_name"),
            "status": row.get("review_status") or "accepted",
            "deal_status": row.get("deal_status") or "",
            "risk_level": row.get("result_grade") or "",
            "watch_flag": bool(row.get("watch_flag")),
            "review_comment": row.get("review_comment") or "",
            "return_pct": row.get("return_pct"),
            "max_return_pct": row.get("max_return_pct"),
            "drawdown_pct": row.get("drawdown_pct"),
            "holding_days": row.get("holding_days"),
            "data_quality": row.get("data_quality") or "",
            "market_data_source": row.get("market_data_source") or "",
            "fallback_used": bool(row.get("fallback_used")),
            "created_at": row.get("created_at"),
        }
