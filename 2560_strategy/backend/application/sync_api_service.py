"""Application service for market data synchronization tasks."""

from __future__ import annotations

from datetime import date, timedelta

from backend.infrastructure.market_data.factory import create_fallback_market_data_provider
from backend.infrastructure.market_data.provider import MarketDataProvider
from backend.infrastructure.tasks.queue import enqueue_task


class SyncApiService:
    def __init__(self, market_data_provider: MarketDataProvider | None = None):
        self.market_data_provider = market_data_provider or create_fallback_market_data_provider()

    def _sync_market_data(self, symbols: list[str], start_date: str, end_date: str, adjust: str) -> dict:
        synced = []
        total = len(symbols)
        for index, symbol in enumerate(symbols, start=1):
            bars = self.market_data_provider.get_daily_bars(symbol, start_date, end_date, adjust=adjust)
            synced.append({"symbol": symbol, "bars": len(bars), "source": bars[0].source if bars else self.market_data_provider.name})
        return {
            "symbols": synced,
            "start_date": start_date,
            "end_date": end_date,
            "adjust": adjust,
            "requested_symbols": total,
            "synced_symbols": len(synced),
            "progress": {"current": total, "total": total, "percent": 100 if total else 0},
        }

    def enqueue_market_data_sync(self, tenant_id: int, payload: dict) -> dict:
        today = date.today()
        symbols = payload.get("symbols") or ["000001", "600519"]
        start_date = payload.get("start_date") or (today - timedelta(days=7)).isoformat()
        end_date = payload.get("end_date") or today.isoformat()
        adjust = payload.get("adjust") or "qfq"
        task = enqueue_task(
            "market.sync",
            self._sync_market_data,
            symbols,
            start_date,
            end_date,
            adjust,
            tenant_id=tenant_id,
            payload={"symbols": symbols, "start_date": start_date, "end_date": end_date, "adjust": adjust},
        )
        return task
