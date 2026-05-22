"""Application service for market data synchronization tasks."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any

from backend.infrastructure.cache.redis_client import get_json, set_json
from backend.infrastructure.market_data.factory import create_fallback_market_data_provider
from backend.infrastructure.market_data.provider import MarketDataProvider
from backend.infrastructure.market_data.utils import BAR_INTERVAL_ALIASES, infer_exchange, infer_security_type, normalize_bar_interval
from backend.infrastructure.tasks.queue import append_current_task_event, enqueue_task
from backend.core.errors import AppError
from backend.repositories import market_data_repo, paper_trading_repo


ALLOWED_ADJUSTS = {"qfq", "hfq", "none", "raw", "bfq", "不复权"}
ALLOWED_SECURITY_TYPES = {"stock", "etf", "index", "convertible_bond", "bond", "fund", "b_share", "other"}


class SyncApiService:
    def __init__(self, market_data_provider: MarketDataProvider | None = None):
        self.market_data_provider = market_data_provider or create_fallback_market_data_provider()

    def _decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        if value in (None, ""):
            return default
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return default

    def _resolve_symbols(self, symbols: list[str] | str | None, *, max_symbols: int = 0, security_type: str | None = None) -> tuple[list[str], dict]:
        requested_all = False
        normalized_security_type = str(security_type or "").strip().lower()
        if isinstance(symbols, str):
            raw_symbols = [item.strip() for item in symbols.split(",") if item.strip()]
        else:
            raw_symbols = [str(item or "").strip() for item in (symbols or []) if str(item or "").strip()]
        if not raw_symbols:
            raw_symbols = ["000001", "600519"]
        if any(item.lower() == "all" for item in raw_symbols):
            requested_all = True
            local_limit = max(max_symbols, 20000)
            local_stocks = market_data_repo.list_stocks(limit=local_limit, security_type=normalized_security_type or None)
            if local_stocks.get("items"):
                raw_symbols = [item.get("symbol") for item in local_stocks.get("items", []) if item.get("symbol")]
            else:
                stocks = self.market_data_provider.get_stock_list()
                if normalized_security_type:
                    stocks = [item for item in stocks if infer_security_type(item.symbol, item.name) == normalized_security_type]
                market_data_repo.upsert_stocks(stocks)
                raw_symbols = [item.symbol for item in stocks if item.symbol]
        limit = max(0, int(max_symbols or 0))
        if limit:
            raw_symbols = raw_symbols[:limit]
        seen = set()
        unique_symbols = []
        for symbol in raw_symbols:
            if symbol in seen:
                continue
            seen.add(symbol)
            unique_symbols.append(symbol)
        return unique_symbols, {
            "requested_all": requested_all,
            "resolved_symbols": len(unique_symbols),
            "max_symbols": limit,
            "security_type": normalized_security_type,
        }

    def _normalize_provider_adjust(self, adjust: str) -> str:
        normalized = str(adjust or "qfq").strip().lower()
        return "none" if normalized in {"none", "raw", "bfq", "不复权"} else normalized

    def _normalize_storage_adjust(self, adjust: str) -> str:
        normalized = str(adjust or "qfq").strip().lower()
        if normalized in {"", "none", "raw", "bfq", "不复权"}:
            return "none"
        return normalized

    def _is_all_symbols(self, symbols: list[str] | str | None) -> bool:
        if isinstance(symbols, str):
            return symbols.strip().lower() == "all"
        return any(str(item or "").strip().lower() == "all" for item in (symbols or []))

    def _chunked(self, items: list[str], batch_size: int) -> list[list[str]]:
        safe_batch_size = max(1, int(batch_size or 1))
        return [items[index : index + safe_batch_size] for index in range(0, len(items), safe_batch_size)]

    def _local_symbol_names(self, symbols: list[str]) -> dict[str, str]:
        names: dict[str, str] = {}
        for symbol in symbols[:1000]:
            normalized_symbol = str(symbol or "").strip()
            if not normalized_symbol:
                continue
            payload = market_data_repo.list_stocks(keyword=normalized_symbol, limit=5)
            for item in payload.get("items") or []:
                name = str(item.get("name") or "").strip()
                if item.get("symbol") == normalized_symbol and self._usable_symbol_name(normalized_symbol, name):
                    names[normalized_symbol] = name
                    break
        missing = [symbol for symbol in symbols if symbol not in names]
        if missing:
            names.update(self._provider_symbol_names(missing))
        return names

    def _usable_symbol_name(self, symbol: str, name: str) -> bool:
        normalized_name = str(name or "").strip()
        return bool(normalized_name and normalized_name != symbol and "?" not in normalized_name and "\ufffd" not in normalized_name)

    def _provider_symbol_names(self, symbols: list[str]) -> dict[str, str]:
        wanted = {str(symbol or "").strip() for symbol in symbols if str(symbol or "").strip()}
        if not wanted:
            return {}
        try:
            stocks = self.market_data_provider.get_stock_list()
        except Exception:
            return {}
        names: dict[str, str] = {}
        matched = []
        for item in stocks:
            symbol = str(getattr(item, "symbol", "") or "").strip()
            name = str(getattr(item, "name", "") or "").strip()
            if symbol in wanted and self._usable_symbol_name(symbol, name):
                names[symbol] = name
                matched.append(item)
        if matched:
            market_data_repo.upsert_stocks(matched)
        return names

    def _symbol_label(self, symbol: str, names: dict[str, str]) -> str:
        name = str(names.get(symbol) or "").strip()
        return f"{symbol} {name}" if name and name != symbol else symbol

    def _provider_display_name(self) -> str:
        usage = getattr(self.market_data_provider, "last_usage", None)
        actual_provider = str(getattr(usage, "actual_provider", "") or "").strip()
        if actual_provider:
            return actual_provider
        providers = getattr(self.market_data_provider, "providers", None) or []
        if providers:
            return str(getattr(providers[0], "name", "") or self.market_data_provider.name)
        return str(self.market_data_provider.name)

    def _bool_value(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def _item_source(self, items: list[Any]) -> str:
        if not items:
            return self.market_data_provider.name
        first = items[0]
        if isinstance(first, dict):
            return str(first.get("source") or self.market_data_provider.name)
        return str(getattr(first, "source", None) or self.market_data_provider.name)

    def _provider_capabilities(self) -> dict:
        getter = getattr(self.market_data_provider, "get_capabilities", None)
        if not callable(getter):
            return {}
        capabilities = getter()
        if hasattr(capabilities, "to_dict"):
            return capabilities.to_dict()
        return dict(capabilities or {})

    def _snapshot_capabilities(self, snapshots: list[Any]) -> dict:
        for item in snapshots:
            value = item.get("capabilities") if isinstance(item, dict) else getattr(item, "capabilities", None)
            if value:
                return dict(value)
        return self._provider_capabilities()

    def _snapshot_source_quality(self, snapshots: list[Any], capabilities: dict) -> str:
        for item in snapshots:
            value = item.get("source_quality") if isinstance(item, dict) else getattr(item, "source_quality", None)
            if value:
                return str(value)
            order_book = item.get("order_book") if isinstance(item, dict) else getattr(item, "order_book", None)
            if isinstance(order_book, dict) and order_book.get("source_quality"):
                return str(order_book["source_quality"])
        return str(capabilities.get("auction_source_quality") or "unknown")

    def _int_env(self, name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)) or default)
        except (TypeError, ValueError):
            return default

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    def _required_int(self, payload: dict, key: str, default: int = 0, *, min_value: int = 0, max_value: int | None = None) -> int:
        raw = payload.get(key)
        if raw in (None, ""):
            value = default
        else:
            try:
                value = int(raw)
            except (TypeError, ValueError) as exc:
                raise AppError(f"{key} must be an integer") from exc
        if value < min_value:
            raise AppError(f"{key} must be >= {min_value}")
        if max_value is not None and value > max_value:
            raise AppError(f"{key} must be <= {max_value}")
        return value

    def _validate_date_window(self, payload: dict, *, require_start: bool = False) -> tuple[str, str]:
        start_date = str(payload.get("start_date") or "").strip()
        end_date = str(payload.get("end_date") or date.today().isoformat()).strip()
        parsed_start = self._parse_date(start_date) if start_date else None
        parsed_end = self._parse_date(end_date)
        if require_start and not start_date:
            raise AppError("start_date is required")
        if start_date and not parsed_start:
            raise AppError("start_date must use YYYY-MM-DD")
        if not parsed_end:
            raise AppError("end_date must use YYYY-MM-DD")
        if parsed_start and parsed_start > parsed_end:
            raise AppError("start_date must be before or equal to end_date")
        return start_date, end_date

    def _validate_interval(self, value: Any, *, allow_1m: bool = False) -> str:
        text = str(value or "1d").strip().lower()
        interval = normalize_bar_interval(text)
        allowed = set(BAR_INTERVAL_ALIASES.values())
        if not allow_1m:
            allowed.discard("1m")
        if interval not in allowed:
            raise AppError("interval must be one of 1d, 5m, 15m, 30m or 1h")
        return interval

    def _validate_adjust(self, value: Any, *, interval: str) -> str:
        default = "none" if interval != "1d" else "qfq"
        adjust = str(value or default).strip().lower()
        if adjust not in ALLOWED_ADJUSTS:
            raise AppError("adjust must be one of qfq, hfq or none")
        return adjust

    def _validate_security_type(self, value: Any, *, default: str | None = None) -> str | None:
        normalized = str(value or default or "").strip().lower()
        if normalized and normalized not in ALLOWED_SECURITY_TYPES:
            raise AppError("security_type is not supported")
        return normalized or None

    def _symbol_sync_window(
        self,
        symbol: str,
        *,
        requested_start: str | None,
        requested_end: str,
        adjust: str,
        incremental: bool,
        bootstrap_days: int,
        correction_days: int,
        interval: str,
    ) -> tuple[str, str, dict]:
        end = self._parse_date(requested_end) or date.today()
        explicit_start = self._parse_date(requested_start)
        if explicit_start:
            return explicit_start.isoformat(), end.isoformat(), {"mode": "explicit", "latest_local_trade_date": None}
        if not incremental:
            start = end - timedelta(days=max(1, int(bootstrap_days or 180)))
            return start.isoformat(), end.isoformat(), {"mode": "bootstrap", "latest_local_trade_date": None}
        coverage = market_data_repo.get_symbol_coverage(symbol, adjust=adjust, interval=interval)
        latest = self._parse_date(coverage.get("last_trade_date"))
        if latest:
            correction = max(0, int(correction_days or 0))
            start = latest - timedelta(days=correction) if correction else latest + timedelta(days=1)
            return start.isoformat(), end.isoformat(), {
                "mode": "incremental",
                "latest_local_trade_date": latest.isoformat(),
                "correction_days": correction,
            }
        start = end - timedelta(days=max(1, int(bootstrap_days or 180)))
        return start.isoformat(), end.isoformat(), {
            "mode": "bootstrap_missing_symbol",
            "latest_local_trade_date": None,
            "bootstrap_days": max(1, int(bootstrap_days or 180)),
        }

    def _sync_market_data(
        self,
        symbols: list[str] | str,
        start_date: str = "",
        end_date: str = "",
        adjust: str = "qfq",
        max_symbols: int = 0,
        tenant_id: int = 1,
        incremental: bool = False,
        bootstrap_days: int = 180,
        correction_days: int = 3,
        interval: str = "1d",
        security_type: str | None = None,
    ) -> dict:
        synced = []
        errors = []
        normalized_interval = normalize_bar_interval(interval)
        resolved_symbols, symbol_meta = self._resolve_symbols(symbols, max_symbols=max_symbols, security_type=security_type)
        total = len(resolved_symbols)
        symbol_names = self._local_symbol_names(resolved_symbols)
        provider_adjust = self._normalize_provider_adjust(adjust)
        storage_adjust = self._normalize_storage_adjust(adjust)
        if normalized_interval != "1d" and storage_adjust in {"qfq", "hfq"}:
            provider_adjust = ""
            storage_adjust = "none"
        requested_end = end_date or date.today().isoformat()
        mode = "incremental" if incremental else ("explicit" if start_date else "bootstrap")
        provider_display_name = self._provider_display_name()
        sync_run = market_data_repo.create_sync_run(
            tenant_id,
            mode=mode,
            source=provider_display_name,
            adjust=storage_adjust,
            interval=normalized_interval,
            requested_symbols=total,
            payload={
                "symbols": resolved_symbols[:20],
                "symbol_count": total,
                "start_date": start_date,
                "end_date": requested_end,
                "adjust": storage_adjust,
                "interval": normalized_interval,
                "security_type": security_type or "",
                "incremental": bool(incremental),
                "bootstrap_days": bootstrap_days,
                "correction_days": correction_days,
            },
        )
        run_id = sync_run.get("id")
        append_current_task_event(
            f"行情同步开始：共 {total} 个标的，数据源 {provider_display_name}，周期 {normalized_interval}，复权 {storage_adjust}",
            progress={"current": 0, "total": total, "percent": 0 if total else 100},
            detail={"run_id": run_id, "mode": mode, "security_type": security_type or ""},
        )
        for index, symbol in enumerate(resolved_symbols, start=1):
            normalized_symbol = str(symbol or "").strip()
            if not normalized_symbol:
                continue
            symbol_label = self._symbol_label(normalized_symbol, symbol_names)
            effective_start, effective_end, window_meta = self._symbol_sync_window(
                normalized_symbol,
                requested_start=start_date,
                requested_end=requested_end,
                adjust=storage_adjust,
                incremental=bool(incremental),
                bootstrap_days=max(1, int(bootstrap_days or 180)),
                correction_days=max(0, int(correction_days or 0)),
                interval=normalized_interval,
            )
            try:
                append_current_task_event(
                    f"[{index}/{total}] {symbol_label} 开始同步，区间 {effective_start} 至 {effective_end}",
                    progress={"current": index - 1, "total": total, "percent": round(((index - 1) / total) * 100, 2) if total else 100},
                    detail={"symbol": normalized_symbol, "name": symbol_names.get(normalized_symbol) or "", "start_date": effective_start, "end_date": effective_end},
                )
                bars = self.market_data_provider.get_daily_bars(normalized_symbol, effective_start, effective_end, adjust=provider_adjust, interval=normalized_interval)
                source = bars[0].source if bars else self.market_data_provider.name
                if not symbol_names.get(normalized_symbol):
                    for bar in bars:
                        name = str(getattr(bar, "name", "") or "").strip()
                        if name:
                            symbol_names[normalized_symbol] = name
                            symbol_label = self._symbol_label(normalized_symbol, symbol_names)
                            break
                market_data_repo.upsert_stocks(
                    [
                        {
                            "symbol": normalized_symbol,
                            "name": symbol_names.get(normalized_symbol) or normalized_symbol,
                            "exchange": infer_exchange(normalized_symbol),
                            "market": "A",
                            "security_type": infer_security_type(normalized_symbol, symbol_names.get(normalized_symbol) or normalized_symbol),
                        }
                    ]
                )
                persisted = market_data_repo.upsert_daily_bars(bars, adjust=storage_adjust)
                first_trade_date = min((bar.trade_date for bar in bars), default=None)
                last_trade_date = max((bar.trade_date for bar in bars), default=None)
                coverage = market_data_repo.get_symbol_coverage(normalized_symbol, adjust=storage_adjust, interval=normalized_interval)
                market_data_repo.upsert_sync_state(
                    tenant_id,
                    symbol=normalized_symbol,
                    source=source,
                    adjust=storage_adjust,
                    interval=normalized_interval,
                    coverage=coverage,
                    status="success",
                )
                market_data_repo.record_sync_run_item(
                    run_id,
                    tenant_id,
                    symbol=normalized_symbol,
                    status="success",
                    start_date=effective_start,
                    end_date=effective_end,
                    bars=len(bars),
                    persisted_bars=persisted,
                    source=source,
                    adjust=storage_adjust,
                    interval=normalized_interval,
                )
                synced.append(
                    {
                        "symbol": normalized_symbol,
                        "bars": len(bars),
                        "persisted_bars": persisted,
                        "source": source,
                        "interval": normalized_interval,
                        "effective_start_date": effective_start,
                        "effective_end_date": effective_end,
                        "window": window_meta,
                        "first_trade_date": first_trade_date.isoformat() if first_trade_date else None,
                        "last_trade_date": last_trade_date.isoformat() if last_trade_date else None,
                        "coverage_end_date": coverage.get("last_trade_date"),
                    }
                )
                append_current_task_event(
                    f"[{index}/{total}] {symbol_label} 同步成功，本次获取 {len(bars)} 条，写入/更新 {persisted} 条，来源 {source}",
                    progress={"current": index, "total": total, "percent": round((index / total) * 100, 2) if total else 100},
                    detail={"symbol": normalized_symbol, "name": symbol_names.get(normalized_symbol) or "", "bars": len(bars), "persisted_bars": persisted, "source": source},
                )
            except Exception as exc:
                message = str(exc)
                errors.append({"symbol": normalized_symbol, "message": message, "effective_start_date": effective_start, "effective_end_date": effective_end})
                market_data_repo.upsert_sync_state(
                    tenant_id,
                    symbol=normalized_symbol,
                    source=provider_display_name,
                    adjust=storage_adjust,
                    interval=normalized_interval,
                    coverage=market_data_repo.get_symbol_coverage(normalized_symbol, adjust=storage_adjust, interval=normalized_interval),
                    status="failed",
                    error=message,
                )
                market_data_repo.record_sync_run_item(
                    run_id,
                    tenant_id,
                    symbol=normalized_symbol,
                    status="failed",
                    start_date=effective_start,
                    end_date=effective_end,
                    source=provider_display_name,
                    adjust=storage_adjust,
                    interval=normalized_interval,
                    error=message,
                )
                append_current_task_event(
                    f"[{index}/{total}] {symbol_label} 同步失败：{message[:300]}",
                    status="running",
                    progress={"current": index, "total": total, "percent": round((index / total) * 100, 2) if total else 100},
                    detail={"symbol": normalized_symbol, "name": symbol_names.get(normalized_symbol) or "", "error": message[:500]},
                )
        if errors and not synced:
            joined = " | ".join(f"{item['symbol']}: {item['message']}" for item in errors[:5])
            market_data_repo.finish_sync_run(run_id, status="failed", result={"synced_symbols": 0, "failed_symbols": len(errors), "persisted_bars": 0, "interval": normalized_interval, "errors": errors[:20]})
            append_current_task_event(
                f"行情同步失败：全部标的失败，共 {len(errors)} 个。原因：{joined[:300]}",
                status="failed",
                progress={"current": total, "total": total, "percent": 100 if total else 0},
                detail={"run_id": run_id, "failed_symbols": len(errors)},
            )
            raise RuntimeError(f"market sync failed for all symbols: {joined}")
        result = {
            "symbols": synced,
            "start_date": start_date,
            "end_date": requested_end,
            "adjust": storage_adjust,
            "interval": normalized_interval,
            "incremental": bool(incremental),
            "bootstrap_days": max(1, int(bootstrap_days or 180)),
            "correction_days": max(0, int(correction_days or 0)),
            "sync_run": sync_run,
            "symbol_resolution": symbol_meta,
            "requested_symbols": total,
            "synced_symbols": len(synced),
            "failed_symbols": len(errors),
            "persisted_bars": sum(int(item.get("persisted_bars") or 0) for item in synced),
            "errors": errors,
            "local_coverage": market_data_repo.coverage_summary(interval=normalized_interval),
            "sync_state_summary": market_data_repo.sync_state_summary(tenant_id, adjust=storage_adjust, interval=normalized_interval),
            "progress": {"current": total, "total": total, "percent": 100 if total else 0},
        }
        market_data_repo.finish_sync_run(run_id, status="completed_with_errors" if errors else "completed", result=result)
        append_current_task_event(
            f"行情同步完成：成功 {len(synced)} 个，失败 {len(errors)} 个，本次写入/更新 {result['persisted_bars']} 条",
            progress=result["progress"],
            detail={"run_id": run_id, "synced_symbols": len(synced), "failed_symbols": len(errors), "persisted_bars": result["persisted_bars"]},
        )
        return result

    def _sync_quote_snapshots(self, symbols: list[str] | str, max_symbols: int = 0, security_type: str | None = None) -> dict:
        resolved_symbols, symbol_meta = self._resolve_symbols(symbols, max_symbols=max_symbols, security_type=security_type)
        snapshots = self.market_data_provider.get_quote_snapshots(resolved_symbols)
        persisted = market_data_repo.upsert_quote_snapshots(snapshots)
        source = self._item_source(snapshots)
        return {
            "requested_symbols": len(resolved_symbols),
            "snapshot_count": len(snapshots),
            "persisted_snapshots": persisted,
            "source": source,
            "symbol_resolution": symbol_meta,
            "local_snapshot_summary": market_data_repo.snapshot_summary(),
            "progress": {"current": len(resolved_symbols), "total": len(resolved_symbols), "percent": 100 if resolved_symbols else 0},
        }

    def _sync_auction_snapshots(
        self,
        symbols: list[str] | str,
        trade_date: str | None = None,
        max_symbols: int = 0,
        security_type: str | None = "stock",
        force: bool = False,
    ) -> dict:
        window = self._auction_window_status(trade_date)
        provider_capabilities = self._provider_capabilities()
        if not force and not window["allowed"]:
            return {
                "status": "skipped",
                "reason": window["reason"],
                "trade_date": trade_date or date.today().isoformat(),
                "window": window,
                "source_quality": provider_capabilities.get("auction_source_quality") or "unknown",
                "capabilities": provider_capabilities,
                "requested_symbols": 0,
                "auction_snapshot_count": 0,
                "persisted_auction_snapshots": 0,
            }
        resolved_symbols, symbol_meta = self._resolve_symbols(symbols, max_symbols=max_symbols, security_type=security_type)
        if not hasattr(self.market_data_provider, "get_auction_snapshots"):
            raise RuntimeError(f"market data provider {self.market_data_provider.name} does not support auction snapshots")
        snapshots = self.market_data_provider.get_auction_snapshots(resolved_symbols, trade_date)
        persisted = market_data_repo.upsert_auction_snapshots(snapshots)
        source = self._item_source(snapshots)
        capabilities = self._snapshot_capabilities(snapshots) or provider_capabilities
        source_quality = self._snapshot_source_quality(snapshots, capabilities)
        return {
            "requested_symbols": len(resolved_symbols),
            "status": "completed",
            "trade_date": trade_date or "",
            "auction_snapshot_count": len(snapshots),
            "persisted_auction_snapshots": persisted,
            "source": source,
            "source_quality": source_quality,
            "capabilities": capabilities,
            "symbol_resolution": symbol_meta,
            "local_auction_snapshot_summary": market_data_repo.auction_snapshot_summary(security_type=security_type),
            "progress": {"current": len(resolved_symbols), "total": len(resolved_symbols), "percent": 100 if resolved_symbols else 0},
        }

    def _auction_window_status(self, trade_date: str | None = None) -> dict:
        now = datetime.now()
        requested = self._parse_date(trade_date) or now.date()
        if requested != now.date():
            return {"allowed": False, "reason": "auction_sync_trade_date_not_today", "now": now.isoformat(timespec="seconds"), "trade_date": requested.isoformat()}
        if now.weekday() >= 5:
            return {"allowed": False, "reason": "auction_sync_non_trading_weekend", "now": now.isoformat(timespec="seconds"), "trade_date": requested.isoformat()}
        start = now.replace(hour=9, minute=20, second=0, microsecond=0)
        end = now.replace(hour=9, minute=25, second=59, microsecond=0)
        if not start <= now <= end:
            return {
                "allowed": False,
                "reason": "auction_sync_outside_0920_0925_window",
                "now": now.isoformat(timespec="seconds"),
                "trade_date": requested.isoformat(),
                "window_start": start.isoformat(timespec="seconds"),
                "window_end": end.isoformat(timespec="seconds"),
            }
        return {"allowed": True, "reason": "within_auction_window", "now": now.isoformat(timespec="seconds"), "trade_date": requested.isoformat()}

    def _indicator_cache_key(self, tenant_id: int, symbol: str, adjust: str, interval: str) -> str:
        return f"indicators:2560:{int(tenant_id or 0)}:{symbol}:{adjust}:{interval}"

    def _indicator_index_key(self, tenant_id: int, adjust: str, interval: str) -> str:
        return f"indicators:2560:index:{int(tenant_id or 0)}:{adjust}:{interval}"

    def _indicator_payload(self, symbol: str, bars: list[dict], *, adjust: str, interval: str) -> dict:
        closes = [self._decimal(item.get("close")) for item in bars if self._decimal(item.get("close")) > 0]
        highs = [self._decimal(item.get("high")) for item in bars if self._decimal(item.get("high")) > 0]
        volumes = [self._decimal(item.get("volume")) for item in bars if self._decimal(item.get("volume")) >= 0]
        latest = bars[-1] if bars else {}
        if len(closes) < 60 or len(volumes) < 60:
            return {
                "schema_version": "indicator-cache/2560/v1",
                "symbol": symbol,
                "adjust": adjust,
                "interval": interval,
                "ready": False,
                "reason": "insufficient_local_bars",
                "bar_count": len(bars),
            }

        ma25 = sum(closes[-25:]) / Decimal(25)
        ma60 = sum(closes[-60:]) / Decimal(60)
        mavol5 = sum(volumes[-5:]) / Decimal(5)
        mavol60 = sum(volumes[-60:]) / Decimal(60)
        latest_close = closes[-1]
        latest_volume = volumes[-1]
        vr5_60 = mavol5 / mavol60 if mavol60 else Decimal("0")
        vr1_60 = latest_volume / mavol60 if mavol60 else Decimal("0")
        ma25_slope_5 = (ma25 / (sum(closes[-30:-5]) / Decimal(25))) - 1 if len(closes) >= 30 and sum(closes[-30:-5]) else Decimal("0")
        ma60_slope_10 = (ma60 / (sum(closes[-70:-10]) / Decimal(60))) - 1 if len(closes) >= 70 and sum(closes[-70:-10]) else Decimal("0")
        high20 = max(highs[-21:-1]) if len(highs) >= 21 else max(highs[-20:])
        if vr1_60 >= Decimal("3"):
            volume_phase = "extreme_risk"
        elif vr1_60 >= Decimal("1.3"):
            volume_phase = "breakout_expand"
        elif vr5_60 >= Decimal("1.05"):
            volume_phase = "build"
        elif vr5_60 >= Decimal("1"):
            volume_phase = "impulse"
        else:
            volume_phase = "insufficient"
        return {
            "schema_version": "indicator-cache/2560/v1",
            "symbol": symbol,
            "adjust": adjust,
            "interval": interval,
            "ready": True,
            "bar_count": len(bars),
            "latest_bar_time": latest.get("trade_time") or latest.get("trade_date"),
            "source": latest.get("source") or "local",
            "ma25": round(float(ma25), 6),
            "ma60": round(float(ma60), 6),
            "mavol5": round(float(mavol5), 6),
            "mavol60": round(float(mavol60), 6),
            "vr5_60": round(float(vr5_60), 6),
            "vr1_60": round(float(vr1_60), 6),
            "dist25": round(float((latest_close - ma25) / ma25), 6) if ma25 else 0,
            "dist60": round(float((latest_close - ma60) / ma60), 6) if ma60 else 0,
            "ma25_slope_5": round(float(ma25_slope_5), 6),
            "ma60_slope_10": round(float(ma60_slope_10), 6),
            "high20": round(float(high20), 6),
            "volume_phase": volume_phase,
            "computed_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _precompute_2560_indicators(
        self,
        tenant_id: int,
        symbols: list[str] | str = "all",
        adjust: str = "qfq",
        interval: str = "1d",
        max_symbols: int = 0,
        lookback_days: int = 180,
        security_type: str | None = "stock",
    ) -> dict:
        normalized_interval = normalize_bar_interval(interval)
        storage_adjust = self._normalize_storage_adjust(adjust)
        if normalized_interval != "1d" and storage_adjust in {"qfq", "hfq"}:
            storage_adjust = "none"
        resolved_symbols, symbol_meta = self._resolve_symbols(symbols, max_symbols=max_symbols, security_type=security_type)
        end = date.today()
        start = end - timedelta(days=max(90, int(lookback_days or 180)))
        cached = []
        skipped = []
        for symbol in resolved_symbols:
            bars = market_data_repo.get_daily_bars(symbol, start.isoformat(), end.isoformat(), adjust=storage_adjust, interval=normalized_interval)
            payload = self._indicator_payload(symbol, bars, adjust=storage_adjust, interval=normalized_interval)
            if not payload.get("ready"):
                skipped.append({"symbol": symbol, "reason": payload.get("reason"), "bar_count": payload.get("bar_count", 0)})
                continue
            key = self._indicator_cache_key(tenant_id, symbol, storage_adjust, normalized_interval)
            set_json(key, payload, ttl_seconds=7 * 86400)
            cached.append({"symbol": symbol, "cache_key": key, "latest_bar_time": payload.get("latest_bar_time"), "volume_phase": payload.get("volume_phase")})

        index_key = self._indicator_index_key(tenant_id, storage_adjust, normalized_interval)
        existing = get_json(index_key) or {"symbols": []}
        symbols_index = sorted({*(existing.get("symbols") or []), *[item["symbol"] for item in cached]})
        set_json(
            index_key,
            {
                "schema_version": "indicator-cache-index/2560/v1",
                "tenant_id": int(tenant_id or 0),
                "adjust": storage_adjust,
                "interval": normalized_interval,
                "symbols": symbols_index,
                "cached_symbols": len(symbols_index),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
            ttl_seconds=7 * 86400,
        )
        return {
            "schema_version": "indicator-precompute/2560/v1",
            "tenant_id": int(tenant_id or 0),
            "symbol_resolution": symbol_meta,
            "requested_symbols": len(resolved_symbols),
            "cached_symbols": len(cached),
            "skipped_symbols": len(skipped),
            "adjust": storage_adjust,
            "interval": normalized_interval,
            "lookback_days": max(90, int(lookback_days or 180)),
            "cache_index_key": index_key,
            "items": cached[:50],
            "skipped": skipped[:50],
            "progress": {"current": len(resolved_symbols), "total": len(resolved_symbols), "percent": 100 if resolved_symbols else 0},
        }

    def _repair_qfq_bars(
        self,
        tenant_id: int,
        symbols: list[str] | str = "all",
        max_symbols: int = 0,
        correction_days: int = 30,
        interval: str = "1d",
        security_type: str | None = "stock",
    ) -> dict:
        end = date.today()
        start = end - timedelta(days=max(1, int(correction_days or 30)))
        return self._sync_market_data(
            symbols,
            start.isoformat(),
            end.isoformat(),
            "qfq",
            max_symbols,
            tenant_id,
            False,
            max(1, int(correction_days or 30)),
            0,
            normalize_bar_interval(interval),
            security_type,
        )

    def _plan_market_sync(
        self,
        tenant_id: int,
        symbols: list[str] | str,
        start_date: str,
        end_date: str,
        adjust: str,
        max_symbols: int = 0,
        batch_size: int = 200,
        incremental: bool = False,
        bootstrap_days: int = 180,
        correction_days: int = 3,
        interval: str = "1d",
        security_type: str | None = None,
    ) -> dict:
        normalized_interval = normalize_bar_interval(interval)
        resolved_symbols, symbol_meta = self._resolve_symbols(symbols, max_symbols=max_symbols, security_type=security_type)
        batches = self._chunked(resolved_symbols, batch_size)
        tasks = []
        for index, batch_symbols in enumerate(batches, start=1):
            payload = {
                "symbols": batch_symbols,
                "start_date": start_date,
                "end_date": end_date,
                "adjust": adjust,
                "interval": normalized_interval,
                "security_type": security_type or "",
                "max_symbols": 0,
                "incremental": bool(incremental),
                "bootstrap_days": int(bootstrap_days or 180),
                "correction_days": int(correction_days or 0),
                "batch_index": index,
                "batch_total": len(batches),
                "parent": "market.sync.plan",
            }
            task = enqueue_task(
                "market.sync",
                self._sync_market_data,
                batch_symbols,
                start_date,
                end_date,
                adjust,
                0,
                tenant_id,
                bool(incremental),
                int(bootstrap_days or 180),
                int(correction_days or 0),
                normalized_interval,
                security_type,
                tenant_id=tenant_id,
                payload=payload,
                idempotency_key=self._task_key("market.sync", tenant_id, payload),
                max_retries=1,
            )
            tasks.append({"id": task["id"], "status": task["status"], "batch_index": index, "symbols": len(batch_symbols)})
        return {
            "tenant_id": tenant_id,
            "plan": "market.sync.plan",
            "symbol_resolution": symbol_meta,
            "requested_symbols": len(resolved_symbols),
            "batch_size": max(1, int(batch_size or 1)),
            "batch_count": len(batches),
            "interval": normalized_interval,
            "security_type": security_type or "",
            "incremental": bool(incremental),
            "bootstrap_days": int(bootstrap_days or 180),
            "correction_days": int(correction_days or 0),
            "child_tasks": tasks,
            "estimated_total_batches": ceil(len(resolved_symbols) / max(1, int(batch_size or 1))) if resolved_symbols else 0,
            "progress": {"current": 0, "total": len(batches), "percent": 0 if batches else 100},
        }

    def _plan_quote_snapshot_sync(
        self,
        tenant_id: int,
        symbols: list[str] | str,
        max_symbols: int = 0,
        batch_size: int = 500,
        security_type: str | None = None,
    ) -> dict:
        resolved_symbols, symbol_meta = self._resolve_symbols(symbols, max_symbols=max_symbols, security_type=security_type)
        batches = self._chunked(resolved_symbols, batch_size)
        tasks = []
        for index, batch_symbols in enumerate(batches, start=1):
            payload = {
                "symbols": batch_symbols,
                "max_symbols": 0,
                "security_type": security_type or "",
                "batch_index": index,
                "batch_total": len(batches),
                "parent": "market.snapshot.plan",
            }
            task = enqueue_task(
                "market.snapshot",
                self._sync_quote_snapshots,
                batch_symbols,
                0,
                security_type,
                tenant_id=tenant_id,
                payload=payload,
                idempotency_key=self._task_key("market.snapshot", tenant_id, payload),
                max_retries=1,
            )
            tasks.append({"id": task["id"], "status": task["status"], "batch_index": index, "symbols": len(batch_symbols)})
        return {
            "tenant_id": tenant_id,
            "plan": "market.snapshot.plan",
            "symbol_resolution": symbol_meta,
            "requested_symbols": len(resolved_symbols),
            "batch_size": max(1, int(batch_size or 1)),
            "batch_count": len(batches),
            "child_tasks": tasks,
            "estimated_total_batches": ceil(len(resolved_symbols) / max(1, int(batch_size or 1))) if resolved_symbols else 0,
            "progress": {"current": 0, "total": len(batches), "percent": 0 if batches else 100},
        }

    def _task_key(self, name: str, tenant_id: int, payload: dict[str, Any]) -> str:
        symbols = payload.get("symbols")
        symbol_key = ",".join(symbols) if isinstance(symbols, list) else str(symbols)
        return (
            f"{name}:{tenant_id}:{payload.get('start_date', '')}:{payload.get('end_date', '')}:"
            f"{payload.get('adjust', '')}:{payload.get('incremental', '')}:{payload.get('bootstrap_days', '')}:"
            f"{payload.get('correction_days', '')}:{payload.get('interval', '')}:{payload.get('security_type', '')}:"
            f"{payload.get('batch_index', 0)}:{symbol_key[:256]}"
        )

    def enqueue_market_data_sync(self, tenant_id: int, payload: dict) -> dict:
        symbols = payload.get("symbols") or ["000001", "600519"]
        start_date, end_date = self._validate_date_window(payload)
        interval = self._validate_interval(payload.get("interval") or payload.get("bar_interval") or "1d")
        adjust = self._validate_adjust(payload.get("adjust"), interval=interval)
        max_symbols = self._required_int(payload, "max_symbols", 0, min_value=0, max_value=20000)
        security_type = self._validate_security_type(payload.get("security_type"))
        batch_size = self._required_int(payload, "batch_size", 200 if self._is_all_symbols(symbols) else 0, min_value=0, max_value=1000)
        incremental = self._bool_value(payload.get("incremental"), self._bool_value(os.getenv("MARKET_SYNC_INCREMENTAL"), True))
        bootstrap_days = self._required_int(payload, "bootstrap_days", self._int_env("MARKET_BOOTSTRAP_DAYS", 180), min_value=1, max_value=3650)
        correction_days = self._required_int(payload, "correction_days", self._int_env("MARKET_SYNC_CORRECTION_DAYS", 3), min_value=0, max_value=365)
        if batch_size > 0:
            return enqueue_task(
                "market.sync.plan",
                self._plan_market_sync,
                tenant_id,
                symbols,
                start_date,
                end_date,
                adjust,
                max_symbols,
                batch_size,
                incremental,
                bootstrap_days,
                correction_days,
                interval,
                security_type,
                tenant_id=tenant_id,
                payload={
                    "symbols": symbols,
                    "start_date": start_date,
                    "end_date": end_date,
                    "adjust": adjust,
                    "interval": interval,
                    "security_type": security_type or "",
                    "max_symbols": max_symbols,
                    "batch_size": batch_size,
                    "incremental": incremental,
                    "bootstrap_days": bootstrap_days,
                    "correction_days": correction_days,
                },
                max_retries=1,
            )
        task = enqueue_task(
            "market.sync",
            self._sync_market_data,
            symbols,
            start_date,
            end_date,
            adjust,
            max_symbols,
            tenant_id,
            incremental,
            bootstrap_days,
            correction_days,
            interval,
            security_type,
            tenant_id=tenant_id,
            payload={
                "symbols": symbols,
                "start_date": start_date,
                "end_date": end_date,
                "adjust": adjust,
                "interval": interval,
                "security_type": security_type or "",
                "max_symbols": max_symbols,
                "incremental": incremental,
                "bootstrap_days": bootstrap_days,
                "correction_days": correction_days,
            },
        )
        return task

    def enqueue_quote_snapshot_sync(self, tenant_id: int, payload: dict) -> dict:
        symbols = payload.get("symbols") or ["000001", "600519"]
        max_symbols = self._required_int(payload, "max_symbols", 0, min_value=0, max_value=20000)
        security_type = self._validate_security_type(payload.get("security_type"))
        batch_size = self._required_int(payload, "batch_size", 500 if self._is_all_symbols(symbols) else 0, min_value=0, max_value=1000)
        if batch_size > 0:
            return enqueue_task(
                "market.snapshot.plan",
                self._plan_quote_snapshot_sync,
                tenant_id,
                symbols,
                max_symbols,
                batch_size,
                security_type,
                tenant_id=tenant_id,
                payload={"symbols": symbols, "max_symbols": max_symbols, "batch_size": batch_size, "security_type": security_type or ""},
                max_retries=1,
            )
        task = enqueue_task(
            "market.snapshot",
            self._sync_quote_snapshots,
            symbols,
            max_symbols,
            security_type,
            tenant_id=tenant_id,
            payload={"symbols": symbols, "max_symbols": max_symbols, "security_type": security_type or ""},
        )
        return task

    def enqueue_paper_position_snapshot_sync(self, tenant_id: int, payload: dict) -> dict:
        account_id = self._required_int(payload, "account_id", 0, min_value=0) or None
        max_symbols = self._required_int(payload, "max_symbols", 200, min_value=0, max_value=20000)
        batch_size = self._required_int(payload, "batch_size", 100, min_value=0, max_value=1000)
        security_type = self._validate_security_type(payload.get("security_type"))
        source = str(payload.get("source") or "paper-position-snapshot").strip()
        scheduled_bucket = payload.get("scheduled_bucket")
        symbols = paper_trading_repo.list_active_position_symbols(tenant_id, account_id=account_id, limit=max_symbols)
        updated_at = datetime.now().isoformat(timespec="seconds")
        if not symbols:
            return {
                "schema_version": "paper-position-snapshot/v1",
                "status": "skipped",
                "skip_reason": "no_active_paper_positions",
                "tenant_id": int(tenant_id or 0),
                "account_id": account_id,
                "symbol_count": 0,
                "symbols": [],
                "updated_at": updated_at,
                "source": source,
                "scheduled_bucket": scheduled_bucket,
                "progress": {"current": 0, "total": 0, "percent": 100},
            }
        snapshot_payload = {
            "symbols": symbols,
            "symbol_count": len(symbols),
            "max_symbols": 0,
            "batch_size": batch_size,
            "security_type": security_type or "",
            "source": source,
            "scheduled_bucket": scheduled_bucket,
            "parent": "paper.positions.snapshot",
            "paper_position_symbol_count": len(symbols),
            "updated_at": updated_at,
            "skip_reason": "",
        }
        if account_id:
            snapshot_payload["account_id"] = account_id
        if batch_size > 0:
            task = enqueue_task(
                "market.snapshot.plan",
                self._plan_quote_snapshot_sync,
                tenant_id,
                symbols,
                0,
                batch_size,
                security_type,
                tenant_id=tenant_id,
                payload=snapshot_payload,
                idempotency_key=f"paper.positions.snapshot.child:{tenant_id}:{account_id or ''}:{scheduled_bucket}:{batch_size}:{security_type or ''}:{','.join(symbols)[:256]}",
                max_retries=1,
                priority=True,
            )
        else:
            task = enqueue_task(
                "market.snapshot",
                self._sync_quote_snapshots,
                symbols,
                0,
                security_type,
                tenant_id=tenant_id,
                payload=snapshot_payload,
                idempotency_key=f"paper.positions.snapshot.child:{tenant_id}:{account_id or ''}:{scheduled_bucket}:{batch_size}:{security_type or ''}:{','.join(symbols)[:256]}",
                max_retries=1,
                priority=True,
            )
        return {
            "schema_version": "paper-position-snapshot/v1",
            "status": "queued",
            "skip_reason": "",
            "tenant_id": int(tenant_id or 0),
            "account_id": account_id,
            "symbol_count": len(symbols),
            "symbols": symbols[:50],
            "updated_at": updated_at,
            "source": source,
            "scheduled_bucket": scheduled_bucket,
            "snapshot_task": {"id": task.get("id"), "name": task.get("name"), "status": task.get("status")},
            "batch_size": batch_size,
            "security_type": security_type or "",
            "progress": {"current": len(symbols), "total": len(symbols), "percent": 100},
        }

    def monitor_paper_positions(self, tenant_id: int, payload: dict) -> dict:
        from backend.application.paper_trading_service import PaperTradingService

        account_id = self._required_int(payload, "account_id", 0, min_value=0) or None
        max_symbols = self._required_int(payload, "max_symbols", 200, min_value=0, max_value=20000)
        batch_size = self._required_int(payload, "batch_size", 100, min_value=0, max_value=1000)
        security_type = self._validate_security_type(payload.get("security_type"))
        source = str(payload.get("source") or "paper-position-monitor").strip()
        scheduled_bucket = payload.get("scheduled_bucket")
        sync_snapshots = self._bool_value(payload.get("sync_snapshots"), True)
        evaluate_exits = self._bool_value(payload.get("evaluate_exits"), True)

        positions = paper_trading_repo.list_positions(tenant_id, account_id=account_id, active_only=True)
        if security_type:
            positions = [item for item in positions if str(item.get("security_type") or "").strip().lower() == security_type]

        symbols = []
        seen = set()
        for position in positions:
            symbol = str(position.get("symbol") or "").strip()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
            if max_symbols and len(symbols) >= max_symbols:
                break
        selected_symbols = set(symbols)
        positions = [item for item in positions if str(item.get("symbol") or "").strip() in selected_symbols]

        updated_at = datetime.now().isoformat(timespec="seconds")
        if not symbols:
            return {
                "schema_version": "paper-position-monitor/v1",
                "status": "skipped",
                "skip_reason": "no_active_paper_positions",
                "tenant_id": int(tenant_id or 0),
                "account_id": account_id,
                "position_count": 0,
                "symbol_count": 0,
                "symbols": [],
                "updated_at": updated_at,
                "source": source,
                "scheduled_bucket": scheduled_bucket,
                "progress": {"current": 0, "total": 0, "percent": 100},
            }

        snapshot_results = []
        if sync_snapshots:
            safe_batch_size = max(1, int(batch_size or len(symbols) or 1))
            for batch_symbols in self._chunked(symbols, safe_batch_size):
                snapshot_results.append(self._sync_quote_snapshots(batch_symbols, 0, security_type))

        paper_service = PaperTradingService()
        account_ids = sorted({int(item.get("account_id") or 0) for item in positions if int(item.get("account_id") or 0)})
        accounts = []
        total_exit_orders = 0
        total_exit_skipped = 0
        total_exit_blocked = 0
        for active_account_id in account_ids:
            monitor_payload = {**payload, "source": source, "account_id": active_account_id}
            mark_result = paper_service.mark_to_market(tenant_id, active_account_id, monitor_payload)
            exit_result = paper_service.evaluate_exits(tenant_id, active_account_id, monitor_payload) if evaluate_exits else {"orders": [], "skipped": [], "blocked": []}
            total_exit_orders += len(exit_result.get("orders") or [])
            total_exit_skipped += len(exit_result.get("skipped") or [])
            total_exit_blocked += len(exit_result.get("blocked") or [])
            accounts.append(
                {
                    "account_id": active_account_id,
                    "mark_to_market": {
                        "updated": mark_result.get("updated", 0),
                        "missing": len(mark_result.get("missing") or []),
                        "stale": len(mark_result.get("stale") or []),
                    },
                    "exits": {
                        "orders": len(exit_result.get("orders") or []),
                        "skipped": len(exit_result.get("skipped") or []),
                        "blocked": len(exit_result.get("blocked") or []),
                    },
                }
            )

        return {
            "schema_version": "paper-position-monitor/v1",
            "status": "completed",
            "skip_reason": "",
            "tenant_id": int(tenant_id or 0),
            "account_id": account_id,
            "position_count": len(positions),
            "symbol_count": len(symbols),
            "symbols": symbols[:50],
            "updated_at": updated_at,
            "source": source,
            "scheduled_bucket": scheduled_bucket,
            "sync_snapshots": sync_snapshots,
            "evaluate_exits": evaluate_exits,
            "snapshot_sync": {
                "batch_count": len(snapshot_results),
                "requested_symbols": sum(int(item.get("requested_symbols") or 0) for item in snapshot_results),
                "snapshot_count": sum(int(item.get("snapshot_count") or 0) for item in snapshot_results),
                "persisted_snapshots": sum(int(item.get("persisted_snapshots") or 0) for item in snapshot_results),
                "source": ",".join(sorted({str(item.get("source") or "") for item in snapshot_results if item.get("source")})),
            },
            "accounts": accounts,
            "exit_summary": {
                "orders": total_exit_orders,
                "skipped": total_exit_skipped,
                "blocked": total_exit_blocked,
            },
            "progress": {"current": len(symbols), "total": len(symbols), "percent": 100},
        }

    def enqueue_auction_snapshot_sync(self, tenant_id: int, payload: dict) -> dict:
        symbols = payload.get("symbols") or "all"
        trade_date = payload.get("trade_date") or date.today().isoformat()
        if not self._parse_date(trade_date):
            raise AppError("trade_date must use YYYY-MM-DD")
        max_symbols = self._required_int(payload, "max_symbols", 0, min_value=0, max_value=20000)
        security_type = self._validate_security_type(payload.get("security_type"), default="stock") or "stock"
        force = self._bool_value(payload.get("force"), False)
        normalized_payload = {
            "symbols": symbols,
            "trade_date": trade_date,
            "max_symbols": max_symbols,
            "security_type": security_type,
            "force": force,
            "phase": "call_auction_0920_0925",
        }
        return enqueue_task(
            "market.auction.sync",
            self._sync_auction_snapshots,
            symbols,
            trade_date,
            max_symbols,
            security_type,
            force,
            tenant_id=tenant_id,
            payload=normalized_payload,
            idempotency_key=f"market.auction.sync:{tenant_id}:{trade_date}:{max_symbols}:{security_type}:{str(symbols)[:256]}",
            max_retries=1,
        )

    def enqueue_indicator_precompute(self, tenant_id: int, payload: dict) -> dict:
        symbols = payload.get("symbols") or "all"
        interval = self._validate_interval(payload.get("interval") or payload.get("bar_interval") or "1d")
        adjust = self._validate_adjust(payload.get("adjust") or "qfq", interval=interval)
        max_symbols = self._required_int(payload, "max_symbols", 0, min_value=0, max_value=20000)
        lookback_days = self._required_int(payload, "lookback_days", 180, min_value=20, max_value=2000)
        security_type = self._validate_security_type(payload.get("security_type"), default="stock") or "stock"
        normalized_payload = {
            "symbols": symbols,
            "adjust": adjust,
            "interval": interval,
            "max_symbols": max_symbols,
            "lookback_days": lookback_days,
            "security_type": security_type,
        }
        return enqueue_task(
            "market.indicators.precompute",
            self._precompute_2560_indicators,
            tenant_id,
            symbols,
            adjust,
            interval,
            max_symbols,
            lookback_days,
            security_type,
            tenant_id=tenant_id,
            payload=normalized_payload,
            idempotency_key=f"market.indicators.precompute:{tenant_id}:{adjust}:{interval}:{max_symbols}:{lookback_days}:{security_type}:{str(symbols)[:256]}",
            max_retries=1,
        )

    def enqueue_qfq_repair(self, tenant_id: int, payload: dict) -> dict:
        symbols = payload.get("symbols") or "all"
        max_symbols = self._required_int(payload, "max_symbols", 0, min_value=0, max_value=20000)
        correction_days = self._required_int(payload, "correction_days", 30, min_value=1, max_value=365)
        interval = self._validate_interval(payload.get("interval") or payload.get("bar_interval") or "1d")
        security_type = self._validate_security_type(payload.get("security_type"), default="stock") or "stock"
        normalized_payload = {
            "symbols": symbols,
            "max_symbols": max_symbols,
            "correction_days": correction_days,
            "interval": interval,
            "security_type": security_type,
        }
        return enqueue_task(
            "market.qfq.repair",
            self._repair_qfq_bars,
            tenant_id,
            symbols,
            max_symbols,
            correction_days,
            interval,
            security_type,
            tenant_id=tenant_id,
            payload=normalized_payload,
            idempotency_key=f"market.qfq.repair:{tenant_id}:{interval}:{max_symbols}:{correction_days}:{security_type}:{str(symbols)[:256]}",
            max_retries=1,
        )
