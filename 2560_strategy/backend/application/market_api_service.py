"""Application service for market data API endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from backend.infrastructure.market_data.factory import create_fallback_market_data_provider
from backend.infrastructure.market_data.provider import MarketDataProvider
from backend.infrastructure.market_data.utils import normalize_bar_interval
from backend.repositories import market_data_repo
from backend.repositories import paper_trading_repo
from backend.repositories import picks_repo


class MarketApiService:
    def __init__(self, market_data_provider: MarketDataProvider | None = None):
        self.market_data_provider = market_data_provider or create_fallback_market_data_provider()

    def list_stocks(self, keyword: str | None = None, limit: int = 20, security_type: str | None = None) -> dict:
        local = market_data_repo.list_stocks(keyword=keyword, limit=limit, security_type=security_type)
        if local.get("items"):
            return local
        stocks = [item.to_dict() for item in self.market_data_provider.get_stock_list()]
        if security_type:
            normalized_type = security_type.strip().lower()
            stocks = [item for item in stocks if str(item.get("security_type") or "").lower() == normalized_type]
        if keyword:
            normalized = keyword.strip().lower()
            stocks = [
                item
                for item in stocks
                if normalized in item["symbol"].lower() or normalized in item["name"].lower()
            ]
        return {"items": stocks[: max(1, min(limit, 200))], "total": len(stocks)}

    def get_kline(self, symbol: str, start_date: str | None = None, end_date: str | None = None, adjust: str = "qfq", interval: str = "1d") -> dict:
        today = date.today()
        normalized_end = end_date or today.isoformat()
        normalized_start = start_date or (today - timedelta(days=90)).isoformat()
        normalized_interval = normalize_bar_interval(interval)
        storage_adjust = self._storage_adjust(adjust)
        provider_adjust = self._provider_adjust(adjust)
        if normalized_interval != "1d" and storage_adjust in {"qfq", "hfq"}:
            storage_adjust = "none"
            provider_adjust = ""
        local_bars = market_data_repo.get_daily_bars(symbol, normalized_start, normalized_end, adjust=storage_adjust, interval=normalized_interval)
        if local_bars:
            sources = sorted({bar.get("source") or "local" for bar in local_bars})
            return {
                "symbol": symbol,
                "start_date": normalized_start,
                "end_date": normalized_end,
                "interval": normalized_interval,
                "adjust": storage_adjust,
                "items": local_bars,
                "total": len(local_bars),
                "provider": "local",
                "market_data_source": ",".join(sources),
                "data_quality": "primary",
                "fallback_used": False,
                "updated_at": date.today().isoformat(),
                "storage": market_data_repo.coverage_summary(interval=normalized_interval),
            }
        bars = self.market_data_provider.get_daily_bars(symbol, normalized_start, normalized_end, adjust=provider_adjust, interval=normalized_interval)
        market_data_repo.upsert_daily_bars(bars, adjust=storage_adjust)
        usage = self._market_data_usage()
        return {
            "symbol": symbol,
            "start_date": normalized_start,
            "end_date": normalized_end,
            "interval": normalized_interval,
            "adjust": storage_adjust,
            "items": [bar.to_dict() for bar in bars],
            "total": len(bars),
            "provider": usage["actual_provider"],
            "market_data_source": usage["actual_provider"],
            "data_quality": usage["data_quality"],
            "fallback_used": usage["fallback_used"],
            "updated_at": date.today().isoformat(),
            "storage": market_data_repo.coverage_summary(interval=normalized_interval),
        }

    def get_stock_context(self, tenant_id: int, symbol: str, limit: int = 20) -> dict:
        normalized_symbol = (symbol or "").strip()
        rows = picks_repo.list_picks(
            "WHERE code=? AND COALESCE(archived,0)=0",
            [normalized_symbol],
            limit=max(1, min(int(limit or 20), 100)),
            tenant_id=tenant_id,
        )
        history = [self._pick_context(row, tenant_id) for row in rows]
        latest_pick = history[0] if history else None
        paper_orders = [
            item
            for item in paper_trading_repo.list_orders(tenant_id, limit=200)
            if str(item.get("symbol") or "").strip() == normalized_symbol
        ][:50]
        trade_signals = [
            item
            for item in paper_trading_repo.list_trade_signals(tenant_id, limit=200)
            if str(item.get("symbol") or "").strip() == normalized_symbol
        ][:50]
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
            "paper_orders": paper_orders,
            "trade_signals": trade_signals,
            "total": len(history),
        }

    def get_market_discovery(self, sample_size: int = 8, lookback_days: int = 45) -> dict:
        today = date.today()
        normalized_sample_size = max(1, min(int(sample_size or 8), 20))
        normalized_lookback_days = max(10, min(int(lookback_days or 45), 180))
        start_date = (today - timedelta(days=normalized_lookback_days)).isoformat()
        end_date = today.isoformat()

        health = self.market_data_provider.health_check()
        stock_universe = self.market_data_provider.get_stock_list() if health.ok else []
        stocks = stock_universe[:normalized_sample_size]
        usage = self._market_data_usage()
        items = []
        provider_errors = list(usage.get("errors") or [])
        sample_errors = []

        for stock in stocks:
            try:
                bars = self.market_data_provider.get_daily_bars(stock.symbol, start_date, end_date, adjust="qfq")
                insight = self._stock_discovery_item(stock.to_dict(), bars)
                items.append(insight)
            except Exception as exc:  # pragma: no cover - provider failures are environment-specific.
                sample_errors.append(f"{stock.symbol}: {exc}")

        advancers = sum(1 for item in items if item["change_pct"] is not None and item["change_pct"] > 0)
        decliners = sum(1 for item in items if item["change_pct"] is not None and item["change_pct"] < 0)
        unchanged = sum(1 for item in items if item["change_pct"] == 0)
        above_ma20 = sum(1 for item in items if item["above_ma20"])
        avg_turnover = self._average([item["turnover_rate"] for item in items])
        top_movers = sorted(
            items,
            key=lambda item: abs(item["change_pct"] or 0),
            reverse=True,
        )[:5]
        active_symbols = sorted(
            items,
            key=lambda item: item["activity_score"],
            reverse=True,
        )[:5]

        total = len(items)
        errors = provider_errors + sample_errors
        coverage = self._market_coverage(
            universe_count=len(stock_universe),
            requested_sample_size=normalized_sample_size,
            sampled_count=len(stocks),
            successful_count=total,
            failed_count=len(sample_errors),
            items=items,
            lookback_days=normalized_lookback_days,
        )
        data_quality_summary = self._market_data_quality_summary(usage, health, coverage, errors)
        return {
            "as_of": end_date,
            "lookback_days": normalized_lookback_days,
            "sample_size": normalized_sample_size,
            "health": health.to_dict(),
            "coverage": coverage,
            "data_quality_summary": data_quality_summary,
            "data_contract": {
                "provider": usage.get("actual_provider") or health.provider,
                "primary_provider": usage.get("primary_provider") or health.provider,
                "provider_chain": usage.get("provider_chain") or [health.provider],
                "data_quality": usage.get("data_quality") or "unknown",
                "fallback_used": bool(usage.get("fallback_used")),
                "provider_errors": provider_errors,
                "sample_errors": sample_errors,
                "errors": errors,
            },
            "breadth": {
                "sampled": total,
                "advancers": advancers,
                "decliners": decliners,
                "unchanged": unchanged,
                "advance_ratio": self._ratio(advancers, total),
                "above_ma20": above_ma20,
                "above_ma20_ratio": self._ratio(above_ma20, total),
                "avg_turnover_rate": avg_turnover,
            },
            "top_movers": top_movers,
            "active_symbols": active_symbols,
            "candidate_groups": self._candidate_groups(items),
            "opportunity_notes": self._market_opportunity_notes(total, advancers, above_ma20, usage),
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

    def _provider_adjust(self, adjust: str) -> str:
        normalized = str(adjust or "qfq").strip().lower()
        return "" if normalized in {"none", "raw", "bfq", "不复权"} else normalized

    def _storage_adjust(self, adjust: str) -> str:
        normalized = str(adjust or "qfq").strip().lower()
        if normalized in {"", "none", "raw", "bfq", "不复权"}:
            return "none"
        return normalized

    def _stock_discovery_item(self, stock: dict, bars: list) -> dict:
        closes = [self._decimal_or_none(getattr(bar, "close", None)) for bar in bars]
        closes = [value for value in closes if value is not None]
        last_bar = bars[-1] if bars else None
        prev_close = closes[-2] if len(closes) >= 2 else None
        last_close = closes[-1] if closes else None
        first_close = closes[0] if closes else None
        ma20_values = closes[-20:]
        ma20 = sum(ma20_values) / Decimal(len(ma20_values)) if ma20_values else None
        change_pct = self._decimal_return(prev_close, last_close)
        lookback_return_pct = self._decimal_return(first_close, last_close)
        turnover_rate = self._decimal_or_none(getattr(last_bar, "turnover_rate", None)) if last_bar else None
        amount = self._decimal_or_none(getattr(last_bar, "amount", None)) if last_bar else None
        activity_score = abs(float(change_pct or 0)) + float(turnover_rate or 0) / 100
        if amount is not None:
            activity_score += min(float(amount) / 1_000_000_000, 5)
        return {
            "symbol": stock.get("symbol"),
            "name": stock.get("name"),
            "exchange": stock.get("exchange") or "",
            "last_trade_date": last_bar.trade_date.isoformat() if last_bar else "",
            "last_close": float(last_close) if last_close is not None else None,
            "change_pct": float(change_pct) if change_pct is not None else None,
            "lookback_return_pct": float(lookback_return_pct) if lookback_return_pct is not None else None,
            "turnover_rate": float(turnover_rate) if turnover_rate is not None else None,
            "amount": float(amount) if amount is not None else None,
            "ma20": float(ma20) if ma20 is not None else None,
            "above_ma20": bool(last_close is not None and ma20 is not None and last_close >= ma20),
            "activity_score": round(activity_score, 4),
            "bars": len(bars),
            "signal_tags": self._signal_tags(change_pct, lookback_return_pct, last_close, ma20),
        }

    def _market_coverage(
        self,
        *,
        universe_count: int,
        requested_sample_size: int,
        sampled_count: int,
        successful_count: int,
        failed_count: int,
        items: list[dict],
        lookback_days: int,
    ) -> dict:
        expected_sample = min(universe_count, requested_sample_size) if universe_count else requested_sample_size
        bars = [int(item.get("bars") or 0) for item in items]
        return {
            "universe_count": universe_count,
            "requested_sample_size": requested_sample_size,
            "sampled": sampled_count,
            "successful": successful_count,
            "failed": failed_count,
            "sample_coverage_rate": self._ratio(sampled_count, expected_sample),
            "success_rate": self._ratio(successful_count, sampled_count),
            "bar_coverage": {
                "lookback_days": lookback_days,
                "min_bars": min(bars) if bars else 0,
                "max_bars": max(bars) if bars else 0,
                "avg_bars": self._average([float(value) for value in bars]) or 0,
                "avg_bar_coverage_rate": self._ratio(round(self._average([float(value) for value in bars]) or 0), lookback_days),
            },
        }

    def _market_data_quality_summary(self, usage: dict, health, coverage: dict, errors: list[str]) -> dict:
        grade = usage.get("data_quality") or ("mock" if health.provider == "mock" else "unknown")
        fallback_used = bool(usage.get("fallback_used"))
        warnings = []
        if grade == "mock":
            warnings.append("mock_market_data")
        if fallback_used:
            warnings.append("fallback_used")
        if coverage["success_rate"] < 1:
            warnings.append("partial_sample_failure")
        if not health.ok:
            warnings.append("provider_unhealthy")
        return {
            "grade": grade,
            "provider": usage.get("actual_provider") or health.provider,
            "primary_provider": usage.get("primary_provider") or health.provider,
            "fallback_used": fallback_used,
            "research_ready": bool(health.ok and grade == "primary" and not fallback_used and coverage["success_rate"] >= 0.8),
            "warnings": warnings,
            "error_count": len(errors),
        }

    def _candidate_groups(self, items: list[dict]) -> list[dict]:
        groups = [
            (
                "momentum_leaders",
                "Momentum leaders",
                "change_pct > 0 and lookback_return_pct >= 3%",
                lambda item: (item.get("change_pct") or 0) > 0 and (item.get("lookback_return_pct") or 0) >= 0.03,
                lambda item: item.get("lookback_return_pct") or 0,
            ),
            (
                "ma20_trend",
                "MA20 trend",
                "last_close >= ma20",
                lambda item: bool(item.get("above_ma20")),
                lambda item: item.get("activity_score") or 0,
            ),
            (
                "high_activity",
                "High activity",
                "top activity_score candidates",
                lambda item: (item.get("activity_score") or 0) > 0,
                lambda item: item.get("activity_score") or 0,
            ),
            (
                "pullback_watch",
                "Pullback watch",
                "positive lookback return with negative latest change",
                lambda item: (item.get("lookback_return_pct") or 0) > 0 and (item.get("change_pct") or 0) < 0,
                lambda item: item.get("lookback_return_pct") or 0,
            ),
        ]
        payload = []
        for key, label, criteria, matcher, sorter in groups:
            matches = sorted([item for item in items if matcher(item)], key=sorter, reverse=True)
            payload.append(
                {
                    "key": key,
                    "label": label,
                    "criteria": criteria,
                    "total": len(matches),
                    "items": [self._candidate_item(item) for item in matches[:5]],
                }
            )
        return payload

    def _candidate_item(self, item: dict) -> dict:
        return {
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "exchange": item.get("exchange") or "",
            "last_close": item.get("last_close"),
            "change_pct": item.get("change_pct"),
            "lookback_return_pct": item.get("lookback_return_pct"),
            "turnover_rate": item.get("turnover_rate"),
            "activity_score": item.get("activity_score"),
            "bars": item.get("bars"),
            "signal_tags": item.get("signal_tags") or [],
        }

    def _signal_tags(self, change_pct: Decimal | None, lookback_return_pct: Decimal | None, last_close: Decimal | None, ma20: Decimal | None) -> list[str]:
        tags: list[str] = []
        if change_pct is not None and change_pct >= Decimal("0.03"):
            tags.append("日内强势")
        if lookback_return_pct is not None and lookback_return_pct >= Decimal("0.08"):
            tags.append("阶段强势")
        if last_close is not None and ma20 is not None and last_close >= ma20:
            tags.append("站上MA20")
        if not tags:
            tags.append("待观察")
        return tags

    def _market_opportunity_notes(self, total: int, advancers: int, above_ma20: int, usage: dict) -> list[str]:
        notes = []
        if usage.get("data_quality") == "mock":
            notes.append("当前为 mock 行情，只能验证产品链路，不能作为研究结论。")
        if usage.get("fallback_used"):
            notes.append("行情源发生 fallback，扫描、回测和复盘结论需要二次复核。")
        if not total:
            notes.append("样本为空，先检查行情源健康和股票列表同步。")
            return notes
        if self._ratio(advancers, total) >= 0.6:
            notes.append("样本上涨家数占优，可优先查看强势样本和扫描入池转化。")
        elif self._ratio(advancers, total) <= 0.3:
            notes.append("样本上涨家数偏低，建议降低扫描结论置信度并控制观察仓位。")
        if self._ratio(above_ma20, total) >= 0.55:
            notes.append("站上 MA20 的样本较多，趋势策略信号可进入复盘验证。")
        return notes

    def _decimal_or_none(self, value) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _decimal_return(self, start: Decimal | None, end: Decimal | None) -> Decimal | None:
        if start in (None, Decimal("0")) or end is None:
            return None
        return (end - start) / start

    def _average(self, values: list[float | None]) -> float | None:
        numeric = [float(value) for value in values if value is not None]
        return round(sum(numeric) / len(numeric), 4) if numeric else None

    def _ratio(self, numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

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
