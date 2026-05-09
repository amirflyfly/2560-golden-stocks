"""Registered handlers for tasks executed by the standalone worker."""

from __future__ import annotations

from collections.abc import Callable


TaskHandler = Callable[[dict], dict]


def _bool_value(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _run_scan_task(task: dict) -> dict:
    from backend.application.scan_api_service import ScanApiService

    payload = task.get("payload") or {}
    strategy_code = payload.get("strategy_code_internal") or payload.get("strategy_code") or "all"
    params = payload.get("params") or {}
    return ScanApiService()._run_scan(int(task.get("tenant_id") or 0), strategy_code, params)


def _run_market_sync_task(task: dict) -> dict:
    from backend.application.sync_api_service import SyncApiService

    payload = task.get("payload") or {}
    symbols = payload.get("symbols") or ["000001", "600519"]
    start_date = payload.get("start_date") or ""
    end_date = payload.get("end_date") or start_date
    adjust = payload.get("adjust") or "qfq"
    interval = payload.get("interval") or payload.get("bar_interval") or "1d"
    security_type = str(payload.get("security_type") or "").strip().lower() or None
    max_symbols = int(payload.get("max_symbols") or 0)
    incremental = _bool_value(payload.get("incremental"), False)
    bootstrap_days = int(payload.get("bootstrap_days") or 180)
    correction_days = int(payload.get("correction_days") or 3)
    return SyncApiService()._sync_market_data(
        symbols,
        start_date,
        end_date,
        adjust,
        max_symbols,
        int(task.get("tenant_id") or 0),
        incremental,
        bootstrap_days,
        correction_days,
        interval,
        security_type,
    )


def _run_market_sync_plan_task(task: dict) -> dict:
    from backend.application.sync_api_service import SyncApiService

    payload = task.get("payload") or {}
    symbols = payload.get("symbols") or "all"
    start_date = payload.get("start_date") or ""
    end_date = payload.get("end_date") or start_date
    adjust = payload.get("adjust") or "qfq"
    interval = payload.get("interval") or payload.get("bar_interval") or "1d"
    security_type = str(payload.get("security_type") or "").strip().lower() or None
    max_symbols = int(payload.get("max_symbols") or 0)
    batch_size = int(payload.get("batch_size") or 200)
    incremental = _bool_value(payload.get("incremental"), False)
    bootstrap_days = int(payload.get("bootstrap_days") or 180)
    correction_days = int(payload.get("correction_days") or 3)
    return SyncApiService()._plan_market_sync(
        int(task.get("tenant_id") or 0),
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
    )


def _run_market_snapshot_task(task: dict) -> dict:
    from backend.application.sync_api_service import SyncApiService

    payload = task.get("payload") or {}
    symbols = payload.get("symbols") or ["000001", "600519"]
    max_symbols = int(payload.get("max_symbols") or 0)
    security_type = str(payload.get("security_type") or "").strip().lower() or None
    return SyncApiService()._sync_quote_snapshots(symbols, max_symbols, security_type)


def _run_market_snapshot_plan_task(task: dict) -> dict:
    from backend.application.sync_api_service import SyncApiService

    payload = task.get("payload") or {}
    symbols = payload.get("symbols") or "all"
    max_symbols = int(payload.get("max_symbols") or 0)
    batch_size = int(payload.get("batch_size") or 500)
    security_type = str(payload.get("security_type") or "").strip().lower() or None
    return SyncApiService()._plan_quote_snapshot_sync(
        int(task.get("tenant_id") or 0),
        symbols,
        max_symbols,
        batch_size,
        security_type,
    )


def _run_market_auction_task(task: dict) -> dict:
    from backend.application.sync_api_service import SyncApiService

    payload = task.get("payload") or {}
    return SyncApiService()._sync_auction_snapshots(
        payload.get("symbols") or "all",
        payload.get("trade_date"),
        int(payload.get("max_symbols") or 0),
        payload.get("security_type") or "stock",
        _bool_value(payload.get("force"), False),
    )


def _run_indicator_precompute_task(task: dict) -> dict:
    from backend.application.sync_api_service import SyncApiService

    payload = task.get("payload") or {}
    return SyncApiService()._precompute_2560_indicators(
        int(task.get("tenant_id") or 0),
        payload.get("symbols") or "all",
        payload.get("adjust") or "qfq",
        payload.get("interval") or payload.get("bar_interval") or "1d",
        int(payload.get("max_symbols") or 0),
        int(payload.get("lookback_days") or 180),
        payload.get("security_type") or "stock",
    )


def _run_qfq_repair_task(task: dict) -> dict:
    from backend.application.sync_api_service import SyncApiService

    payload = task.get("payload") or {}
    return SyncApiService()._repair_qfq_bars(
        int(task.get("tenant_id") or 0),
        payload.get("symbols") or "all",
        int(payload.get("max_symbols") or 0),
        int(payload.get("correction_days") or 30),
        payload.get("interval") or payload.get("bar_interval") or "1d",
        payload.get("security_type") or "stock",
    )


def _run_alert_evaluation_task(task: dict) -> dict:
    from backend.application.alert_service import AlertEvaluationService

    payload = task.get("payload") or {}
    return AlertEvaluationService().evaluate_all(source=payload.get("source") or "worker")


def _run_strategy_production_task(task: dict) -> dict:
    from backend.application.strategy_api_service import StrategyApiService

    payload = task.get("payload") or {}
    return StrategyApiService().run_deployed_strategy(
        int(task.get("tenant_id") or 0),
        int(payload.get("strategy_id") or 0),
        payload.get("params") or {},
    )


def _run_daily_review_task(task: dict) -> dict:
    from backend.application.report_api_service import ReportApiService

    payload = task.get("payload") or {}
    channels = payload.get("channels") if isinstance(payload.get("channels"), list) else None
    return ReportApiService().daily_review(
        int(task.get("tenant_id") or 0),
        payload.get("trade_date"),
        account_id=int(payload["account_id"]) if payload.get("account_id") else None,
        push=_bool_value(payload.get("push"), False),
        channels=channels,
        user_id=int(payload["user_id"]) if payload.get("user_id") else None,
        source=payload.get("source") or "worker",
    )


def _run_external_push_dispatch_task(task: dict) -> dict:
    from backend.application.external_push import dispatch_external_push_task

    return dispatch_external_push_task(task.get("payload") or {})


TASK_HANDLERS: dict[str, TaskHandler] = {
    "scan.run": _run_scan_task,
    "market.sync": _run_market_sync_task,
    "market.sync.plan": _run_market_sync_plan_task,
    "market.snapshot": _run_market_snapshot_task,
    "market.snapshot.plan": _run_market_snapshot_plan_task,
    "market.auction.sync": _run_market_auction_task,
    "market.indicators.precompute": _run_indicator_precompute_task,
    "market.qfq.repair": _run_qfq_repair_task,
    "alerts.evaluate": _run_alert_evaluation_task,
    "external_push.dispatch": _run_external_push_dispatch_task,
    "strategy.production_run": _run_strategy_production_task,
    "reports.daily_review": _run_daily_review_task,
}


def get_task_handler(name: str | None) -> TaskHandler | None:
    return TASK_HANDLERS.get((name or "").strip())
