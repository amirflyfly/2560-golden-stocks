"""Standalone background task worker."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from datetime import datetime

from backend.infrastructure.tasks.handlers import get_task_handler
from backend.infrastructure.tasks.queue import dequeue_task_id, enqueue_task, get_task, list_tasks, mark_stale_tasks, run_queued_task, update_task

_STOP = False


def _request_stop(*_args):
    global _STOP
    _STOP = True


def _fail_unregistered_task(task: dict) -> dict:
    return update_task(
        task["id"],
        {
            "status": "failed",
            "error": f"no registered worker handler for task name {task.get('name')}",
            "failure_category": "validation",
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        },
    ) or task


def work_once() -> dict | None:
    task_id = dequeue_task_id()
    if not task_id:
        return None
    task = get_task(task_id)
    if not task:
        return {"id": task_id, "status": "missing"}
    handler = get_task_handler(task.get("name"))
    if not handler:
        return _fail_unregistered_task(task)
    return run_queued_task(task_id, handler, task)


def _enqueue_alert_evaluation(now: float, interval_seconds: int) -> dict:
    bucket = int(now // max(1, interval_seconds))
    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    return enqueue_task(
        "alerts.evaluate",
        lambda: {"scheduled": True},
        tenant_id=tenant_id,
        payload={"source": "worker-scheduler", "scheduled_bucket": bucket},
        idempotency_key=f"alerts.evaluate:{bucket}",
        max_retries=1,
    )


def _csv_env(name: str, default: str = "") -> list[str] | str:
    value = os.getenv(name, default).strip()
    if value.lower() == "all":
        return "all"
    return [item.strip() for item in value.split(",") if item.strip()]


def _csv_list_env(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default).strip()
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


def _strategy_code_alias(value: str | None) -> str:
    text = str(value or "").strip()
    aliases = {
        "25-60": "2560",
        "25_60": "2560",
        "25/60": "2560",
        "2560": "2560",
        "涨停回马枪": "LIMIT_UP_RETURN",
        "limit_up_return": "LIMIT_UP_RETURN",
        "LIMIT_UP_RETURN": "LIMIT_UP_RETURN",
    }
    return aliases.get(text, aliases.get(text.lower(), text))


def _strategy_code_filter(codes: list[str] | str | None) -> set[str] | None:
    if codes is None:
        return None
    items = _csv_list_env("", codes) if isinstance(codes, str) else codes
    if not items or any(str(item).strip().lower() == "all" for item in items):
        return None
    return {_strategy_code_alias(item) for item in items if str(item).strip()}


def _parse_daily_times(value: str | list[str] | None) -> list[tuple[int, int, str]]:
    items = _csv_list_env("", value or "") if isinstance(value, str) else (value or [])
    parsed: list[tuple[int, int, str]] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        parts = text.split(":")
        if len(parts) != 2:
            continue
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError:
            continue
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            parsed.append((hour, minute, f"{hour:02d}:{minute:02d}"))
    return parsed


def _due_daily_time_buckets(now: float, daily_times: list[tuple[int, int, str]], grace_seconds: int) -> list[tuple[str, str]]:
    current = datetime.fromtimestamp(now)
    due = []
    grace = max(1, int(grace_seconds or 1))
    for hour, minute, label in daily_times:
        scheduled_at = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delay_seconds = (current - scheduled_at).total_seconds()
        if 0 <= delay_seconds < grace:
            due.append((f"{scheduled_at.date().isoformat()}T{label}", label))
    return due


def _scheduled_task_exists(idempotency_key: str) -> bool:
    return any(task.get("idempotency_key") == idempotency_key for task in list_tasks(limit=200, name="strategy.production_run"))


def _scheduled_scan_exists(idempotency_key: str) -> bool:
    return any(task.get("idempotency_key") == idempotency_key for task in list_tasks(limit=200, name="scan.run"))


def _enqueue_market_sync(now: float, interval_seconds: int) -> dict:
    from datetime import date

    bucket = int(now // max(1, interval_seconds))
    end_date = date.today()
    symbols = _csv_env("MARKET_SYNC_SYMBOLS", "000001,600519")
    max_symbols = int(os.getenv("MARKET_SYNC_MAX_SYMBOLS", "0") or 0)
    batch_size = int(os.getenv("MARKET_SYNC_BATCH_SIZE", "200") or 200)
    adjust = os.getenv("MARKET_SYNC_ADJUST", "qfq")
    interval = os.getenv("MARKET_SYNC_INTERVAL", os.getenv("MARKET_SYNC_BAR_INTERVAL", "1d"))
    security_type = os.getenv("MARKET_SYNC_SECURITY_TYPE", "").strip().lower()
    incremental = os.getenv("MARKET_SYNC_INCREMENTAL", "1").strip().lower() not in {"0", "false", "no"}
    bootstrap_days = int(os.getenv("MARKET_BOOTSTRAP_DAYS", "180") or 180)
    correction_days = int(os.getenv("MARKET_SYNC_CORRECTION_DAYS", "3") or 3)
    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    return enqueue_task(
        "market.sync.plan" if batch_size > 0 else "market.sync",
        lambda: {"scheduled": True},
        tenant_id=tenant_id,
        payload={
            "symbols": symbols,
            "start_date": "",
            "end_date": end_date.isoformat(),
            "adjust": adjust,
            "interval": interval,
            "security_type": security_type,
            "max_symbols": max_symbols,
            "batch_size": batch_size,
            "incremental": incremental,
            "bootstrap_days": bootstrap_days,
            "correction_days": correction_days,
            "source": "worker-scheduler",
            "scheduled_bucket": bucket,
        },
        idempotency_key=f"market.sync:{bucket}:{symbols}:{adjust}:{interval}:{security_type}:{max_symbols}:{batch_size}:{incremental}:{bootstrap_days}:{correction_days}",
        max_retries=1,
    )


def _enqueue_market_bootstrap(now: float) -> dict:
    from datetime import date

    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    symbols = _csv_env("MARKET_BOOTSTRAP_SYMBOLS", os.getenv("MARKET_SYNC_SYMBOLS", "all"))
    max_symbols = int(os.getenv("MARKET_BOOTSTRAP_MAX_SYMBOLS", os.getenv("MARKET_SYNC_MAX_SYMBOLS", "0")) or 0)
    batch_size = int(os.getenv("MARKET_BOOTSTRAP_BATCH_SIZE", os.getenv("MARKET_SYNC_BATCH_SIZE", "200")) or 200)
    adjust = os.getenv("MARKET_SYNC_ADJUST", "qfq")
    interval = os.getenv("MARKET_SYNC_INTERVAL", os.getenv("MARKET_SYNC_BAR_INTERVAL", "1d"))
    security_type = os.getenv("MARKET_SYNC_SECURITY_TYPE", "").strip().lower()
    bootstrap_days = int(os.getenv("MARKET_BOOTSTRAP_DAYS", "180") or 180)
    bucket = date.today().isoformat()
    return enqueue_task(
        "market.sync.plan" if batch_size > 0 else "market.sync",
        lambda: {"scheduled": True},
        tenant_id=tenant_id,
        payload={
            "symbols": symbols,
            "start_date": "",
            "end_date": date.today().isoformat(),
            "adjust": adjust,
            "interval": interval,
            "security_type": security_type,
            "max_symbols": max_symbols,
            "batch_size": batch_size,
            "incremental": False,
            "bootstrap_days": bootstrap_days,
            "correction_days": 0,
            "source": "worker-bootstrap",
            "scheduled_bucket": bucket,
        },
        idempotency_key=f"market.bootstrap:{tenant_id}:{bucket}:{symbols}:{adjust}:{interval}:{security_type}:{max_symbols}:{batch_size}:{bootstrap_days}",
        max_retries=1,
    )


def _enqueue_market_snapshot(now: float, interval_seconds: int) -> dict:
    bucket = int(now // max(1, interval_seconds))
    symbols = _csv_env("MARKET_SNAPSHOT_SYMBOLS", os.getenv("MARKET_SYNC_SYMBOLS", "000001,600519"))
    max_symbols = int(os.getenv("MARKET_SNAPSHOT_MAX_SYMBOLS", os.getenv("MARKET_SYNC_MAX_SYMBOLS", "0")) or 0)
    batch_size = int(os.getenv("MARKET_SNAPSHOT_BATCH_SIZE", "500") or 500)
    security_type = os.getenv("MARKET_SNAPSHOT_SECURITY_TYPE", os.getenv("MARKET_SYNC_SECURITY_TYPE", "")).strip().lower()
    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    return enqueue_task(
        "market.snapshot.plan" if batch_size > 0 else "market.snapshot",
        lambda: {"scheduled": True},
        tenant_id=tenant_id,
        payload={
            "symbols": symbols,
            "max_symbols": max_symbols,
            "batch_size": batch_size,
            "security_type": security_type,
            "source": "worker-scheduler",
            "scheduled_bucket": bucket,
        },
        idempotency_key=f"market.snapshot:{bucket}:{symbols}:{security_type}:{max_symbols}:{batch_size}",
        max_retries=1,
    )


def _enqueue_paper_position_snapshot(now: float, interval_seconds: int) -> dict:
    bucket = int(now // max(1, interval_seconds))
    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    account_id = os.getenv("PAPER_POSITION_SNAPSHOT_ACCOUNT_ID", "").strip()
    max_symbols = int(os.getenv("PAPER_POSITION_SNAPSHOT_MAX_SYMBOLS", "200") or 200)
    batch_size = int(os.getenv("PAPER_POSITION_SNAPSHOT_BATCH_SIZE", "100") or 100)
    security_type = os.getenv("PAPER_POSITION_SNAPSHOT_SECURITY_TYPE", os.getenv("MARKET_SNAPSHOT_SECURITY_TYPE", "")).strip().lower()
    payload = {
        "account_id": int(account_id) if account_id else None,
        "max_symbols": max_symbols,
        "batch_size": batch_size,
        "security_type": security_type,
        "source": "worker-paper-position-scheduler",
        "scheduled_bucket": bucket,
        "skip_reason": "",
    }
    return enqueue_task(
        "paper.positions.snapshot",
        lambda: {"scheduled": True},
        tenant_id=tenant_id,
        payload=payload,
        idempotency_key=f"paper.positions.snapshot:{tenant_id}:{account_id}:{bucket}:{max_symbols}:{batch_size}:{security_type}",
        max_retries=1,
        priority=True,
    )


def _enqueue_paper_position_monitor(now: float, interval_seconds: int) -> dict:
    bucket = int(now // max(1, interval_seconds))
    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    account_id = os.getenv("PAPER_POSITION_MONITOR_ACCOUNT_ID", os.getenv("PAPER_POSITION_SNAPSHOT_ACCOUNT_ID", "")).strip()
    max_symbols = int(os.getenv("PAPER_POSITION_MONITOR_MAX_SYMBOLS", os.getenv("PAPER_POSITION_SNAPSHOT_MAX_SYMBOLS", "200")) or 200)
    batch_size = int(os.getenv("PAPER_POSITION_MONITOR_BATCH_SIZE", "100") or 100)
    security_type = os.getenv("PAPER_POSITION_MONITOR_SECURITY_TYPE", os.getenv("PAPER_POSITION_SNAPSHOT_SECURITY_TYPE", "")).strip().lower()
    sync_snapshots = _bool_env("PAPER_POSITION_MONITOR_SYNC_SNAPSHOTS", "1")
    evaluate_exits = _bool_env("PAPER_POSITION_MONITOR_EVALUATE_EXITS", "1")
    payload = {
        "account_id": int(account_id) if account_id else None,
        "max_symbols": max_symbols,
        "batch_size": batch_size,
        "security_type": security_type,
        "sync_snapshots": sync_snapshots,
        "evaluate_exits": evaluate_exits,
        "source": "worker-paper-position-monitor",
        "scheduled_bucket": bucket,
        "skip_reason": "",
    }
    return enqueue_task(
        "paper.positions.monitor",
        lambda: {"scheduled": True},
        tenant_id=tenant_id,
        payload=payload,
        idempotency_key=f"paper.positions.monitor:{tenant_id}:{account_id}:{bucket}:{max_symbols}:{batch_size}:{security_type}:{sync_snapshots}:{evaluate_exits}",
        max_retries=1,
        priority=True,
    )


def _enqueue_indicator_precompute(now: float, interval_seconds: int) -> dict:
    bucket = int(now // max(1, interval_seconds))
    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    symbols = _csv_env("INDICATOR_PRECOMPUTE_SYMBOLS", os.getenv("MARKET_SYNC_SYMBOLS", "all"))
    max_symbols = int(os.getenv("INDICATOR_PRECOMPUTE_MAX_SYMBOLS", os.getenv("MARKET_SYNC_MAX_SYMBOLS", "0")) or 0)
    lookback_days = int(os.getenv("INDICATOR_PRECOMPUTE_LOOKBACK_DAYS", "180") or 180)
    adjust = os.getenv("INDICATOR_PRECOMPUTE_ADJUST", os.getenv("MARKET_SYNC_ADJUST", "qfq"))
    interval = os.getenv("INDICATOR_PRECOMPUTE_INTERVAL", "1d")
    security_type = os.getenv("INDICATOR_PRECOMPUTE_SECURITY_TYPE", "stock")
    return enqueue_task(
        "market.indicators.precompute",
        lambda: {"scheduled": True},
        tenant_id=tenant_id,
        payload={
            "symbols": symbols,
            "adjust": adjust,
            "interval": interval,
            "max_symbols": max_symbols,
            "lookback_days": lookback_days,
            "security_type": security_type,
            "source": "worker-scheduler",
            "scheduled_bucket": bucket,
        },
        idempotency_key=f"market.indicators.precompute:{tenant_id}:{bucket}:{symbols}:{adjust}:{interval}:{max_symbols}:{lookback_days}:{security_type}",
        max_retries=1,
    )


def _enqueue_qfq_repair(now: float, interval_seconds: int) -> dict:
    bucket = int(now // max(1, interval_seconds))
    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    symbols = _csv_env("QFQ_REPAIR_SYMBOLS", os.getenv("MARKET_SYNC_SYMBOLS", "all"))
    max_symbols = int(os.getenv("QFQ_REPAIR_MAX_SYMBOLS", os.getenv("MARKET_SYNC_MAX_SYMBOLS", "0")) or 0)
    correction_days = int(os.getenv("QFQ_REPAIR_CORRECTION_DAYS", "30") or 30)
    security_type = os.getenv("QFQ_REPAIR_SECURITY_TYPE", "stock")
    return enqueue_task(
        "market.qfq.repair",
        lambda: {"scheduled": True},
        tenant_id=tenant_id,
        payload={
            "symbols": symbols,
            "max_symbols": max_symbols,
            "correction_days": correction_days,
            "interval": "1d",
            "security_type": security_type,
            "source": "worker-scheduler",
            "scheduled_bucket": bucket,
        },
        idempotency_key=f"market.qfq.repair:{tenant_id}:{bucket}:{symbols}:{max_symbols}:{correction_days}:{security_type}",
        max_retries=1,
    )


def _enqueue_strategy_scans(
    now: float,
    *,
    strategy_codes: list[str] | str,
    source: str = "worker-scan-scheduler",
    scheduled_bucket: str | int | None = None,
    skip_existing: bool = False,
) -> dict:
    bucket = scheduled_bucket if scheduled_bucket is not None else datetime.fromtimestamp(now).date().isoformat()
    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    scan_limit = int(os.getenv("STRATEGY_SCAN_DAILY_SCAN_LIMIT", os.getenv("STRATEGY_RUN_SCAN_LIMIT", "6000")) or 6000)
    codes = _strategy_code_filter(strategy_codes) or set()
    tasks = []
    for strategy_code in sorted(codes):
        idempotency_key = f"scan.run.daily:{bucket}:{tenant_id}:{strategy_code}:{scan_limit}"
        if skip_existing and _scheduled_scan_exists(idempotency_key):
            tasks.append({"id": None, "strategy_code": strategy_code, "status": "already_scheduled"})
            continue
        params = {
            "full_universe": True,
            "local_only": True,
            "scan_limit": scan_limit,
            "sample_size": min(20, scan_limit),
            "source": source,
            "scheduled_bucket": bucket,
            "disable_market_sample_fallback": True,
        }
        task = enqueue_task(
            "scan.run",
            lambda: {"scheduled": True},
            tenant_id=tenant_id,
            payload={
                "strategy_code": strategy_code,
                "strategy_code_internal": strategy_code,
                "params": params,
            },
            idempotency_key=idempotency_key,
            max_retries=1,
        )
        tasks.append({"id": task["id"], "strategy_code": strategy_code, "status": task["status"]})
    return {"scheduled_scans": len(tasks), "tasks": tasks, "bucket": bucket, "source": source}


def _enqueue_strategy_runs(
    now: float,
    interval_seconds: int,
    *,
    strategy_codes: list[str] | str | None = None,
    source: str = "worker-scheduler",
    scheduled_bucket: str | int | None = None,
    skip_existing: bool = False,
) -> dict:
    from backend.repositories import strategy_repo

    bucket = scheduled_bucket if scheduled_bucket is not None else int(now // max(1, interval_seconds))
    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    scan_limit = int(os.getenv("STRATEGY_RUN_SCAN_LIMIT", "6000") or 6000)
    min_coverage_ratio = float(os.getenv("STRATEGY_RUN_MIN_COVERAGE_RATIO", "0") or 0)
    allowed_codes = _strategy_code_filter(strategy_codes)
    tasks = []
    for strategy in strategy_repo.list_strategies(active_only=True):
        if strategy.get("lifecycle_status") != "deployed" or not strategy.get("enabled"):
            continue
        strategy_code = _strategy_code_alias(strategy.get("code"))
        if allowed_codes is not None and strategy_code not in allowed_codes:
            continue
        idempotency_key = f"strategy.production_run:{bucket}:{tenant_id}:{strategy.get('id')}:{scan_limit}"
        if skip_existing and _scheduled_task_exists(idempotency_key):
            tasks.append({"id": None, "strategy_id": strategy.get("id"), "strategy_code": strategy.get("code"), "status": "already_scheduled"})
            continue
        payload = {
            "strategy_id": strategy.get("id"),
            "strategy_code": strategy.get("code"),
            "params": {
                "full_universe": True,
                "local_only": True,
                "scan_limit": scan_limit,
                "min_coverage_ratio": min_coverage_ratio,
                "source": source,
                "scheduled_bucket": bucket,
            },
        }
        task = enqueue_task(
            "strategy.production_run",
            lambda: {"scheduled": True},
            tenant_id=tenant_id,
            payload=payload,
            idempotency_key=idempotency_key,
            max_retries=1,
        )
        tasks.append({"id": task["id"], "strategy_id": strategy.get("id"), "strategy_code": strategy.get("code"), "status": task["status"]})
    return {"scheduled_strategies": len(tasks), "tasks": tasks, "bucket": bucket, "source": source}


def _enqueue_daily_review(now: float, interval_seconds: int) -> dict:
    from datetime import date

    bucket = int(now // max(1, interval_seconds))
    tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
    account_id = os.getenv("DAILY_REVIEW_ACCOUNT_ID", "").strip()
    user_id = os.getenv("DAILY_REVIEW_USER_ID", "").strip()
    channels = _csv_list_env("DAILY_REVIEW_CHANNELS", "")
    push = _bool_env("DAILY_REVIEW_PUSH", "0")
    evaluate_exits = _bool_env("DAILY_REVIEW_EVALUATE_EXITS", "1")
    trade_date = os.getenv("DAILY_REVIEW_TRADE_DATE", "").strip() or date.today().isoformat()
    payload = {
        "trade_date": trade_date,
        "account_id": int(account_id) if account_id else None,
        "user_id": int(user_id) if user_id else None,
        "push": push,
        "evaluate_exits": evaluate_exits,
        "channels": channels,
        "source": "worker-scheduler",
        "scheduled_bucket": bucket,
    }
    return enqueue_task(
        "reports.daily_review",
        lambda: {"scheduled": True},
        tenant_id=tenant_id,
        payload=payload,
        idempotency_key=f"reports.daily_review:{tenant_id}:{trade_date}:{bucket}:{account_id}:{user_id}:{push}:{evaluate_exits}:{','.join(channels)}",
        max_retries=1,
    )


def run_worker(
    *,
    poll_seconds: float = 1.0,
    once: bool = False,
    alert_interval_seconds: int = 0,
    market_sync_interval_seconds: int = 0,
    market_snapshot_interval_seconds: int = 0,
    paper_position_snapshot_interval_seconds: int = 0,
    paper_position_monitor_interval_seconds: int = 0,
    indicator_precompute_interval_seconds: int = 0,
    qfq_repair_interval_seconds: int = 0,
    strategy_run_interval_seconds: int = 0,
    strategy_run_daily_times: str = "",
    strategy_run_daily_strategies: str = "",
    strategy_run_daily_grace_seconds: int = 900,
    strategy_scan_daily_times: str = "",
    strategy_scan_daily_strategies: str = "",
    strategy_scan_daily_grace_seconds: int = 900,
    daily_review_interval_seconds: int = 0,
    bootstrap_on_start: bool = False,
) -> int:
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    processed = 0
    if bootstrap_on_start and not once:
        bootstrap_task = _enqueue_market_bootstrap(time.time())
        print(json.dumps({"scheduled": "market.bootstrap", "task_id": bootstrap_task.get("id"), "status": bootstrap_task.get("status")}, ensure_ascii=False), flush=True)
    next_alert_eval_at = time.time() if alert_interval_seconds > 0 and not once else None
    next_market_sync_at = time.time() if market_sync_interval_seconds > 0 and not once else None
    next_market_snapshot_at = time.time() if market_snapshot_interval_seconds > 0 and not once else None
    next_paper_position_snapshot_at = time.time() if paper_position_snapshot_interval_seconds > 0 and not once else None
    next_paper_position_monitor_at = time.time() if paper_position_monitor_interval_seconds > 0 and not once else None
    next_indicator_precompute_at = time.time() if indicator_precompute_interval_seconds > 0 and not once else None
    next_qfq_repair_at = time.time() + max(1, qfq_repair_interval_seconds) if qfq_repair_interval_seconds > 0 and not once else None
    next_strategy_run_at = time.time() if strategy_run_interval_seconds > 0 and not once else None
    daily_strategy_times = _parse_daily_times(strategy_run_daily_times) if not once else []
    daily_strategy_buckets: set[str] = set()
    daily_scan_times = _parse_daily_times(strategy_scan_daily_times) if not once else []
    daily_scan_buckets: set[str] = set()
    next_daily_review_at = time.time() if daily_review_interval_seconds > 0 and not once else None
    while not _STOP:
        mark_stale_tasks()
        now = time.time()
        if daily_scan_times:
            today = datetime.fromtimestamp(now).date().isoformat()
            daily_scan_buckets = {bucket for bucket in daily_scan_buckets if bucket.startswith(today)}
            for bucket, label in _due_daily_time_buckets(now, daily_scan_times, strategy_scan_daily_grace_seconds):
                if bucket in daily_scan_buckets:
                    continue
                scheduled = _enqueue_strategy_scans(
                    now,
                    strategy_codes=strategy_scan_daily_strategies,
                    source="worker-daily-scan-scheduler",
                    scheduled_bucket=bucket,
                    skip_existing=True,
                )
                print(json.dumps({"scheduled": "scan.run.daily", "scheduled_time": label, **scheduled}, ensure_ascii=False), flush=True)
                daily_scan_buckets.add(bucket)
        if daily_strategy_times:
            today = datetime.fromtimestamp(now).date().isoformat()
            daily_strategy_buckets = {bucket for bucket in daily_strategy_buckets if bucket.startswith(today)}
            for bucket, label in _due_daily_time_buckets(now, daily_strategy_times, strategy_run_daily_grace_seconds):
                if bucket in daily_strategy_buckets:
                    continue
                scheduled = _enqueue_strategy_runs(
                    now,
                    86400,
                    strategy_codes=strategy_run_daily_strategies,
                    source="worker-daily-scheduler",
                    scheduled_bucket=bucket,
                    skip_existing=True,
                )
                print(json.dumps({"scheduled": "strategy.production_run.daily", "scheduled_time": label, **scheduled}, ensure_ascii=False), flush=True)
                daily_strategy_buckets.add(bucket)
        if next_alert_eval_at is not None and now >= next_alert_eval_at:
            _enqueue_alert_evaluation(now, alert_interval_seconds)
            next_alert_eval_at = now + max(1, alert_interval_seconds)
        if next_market_sync_at is not None and now >= next_market_sync_at:
            _enqueue_market_sync(now, market_sync_interval_seconds)
            next_market_sync_at = now + max(1, market_sync_interval_seconds)
        if next_market_snapshot_at is not None and now >= next_market_snapshot_at:
            _enqueue_market_snapshot(now, market_snapshot_interval_seconds)
            next_market_snapshot_at = now + max(1, market_snapshot_interval_seconds)
        if next_paper_position_snapshot_at is not None and now >= next_paper_position_snapshot_at:
            paper_snapshot_task = _enqueue_paper_position_snapshot(now, paper_position_snapshot_interval_seconds)
            print(json.dumps({"scheduled": "paper.positions.snapshot", "task_id": paper_snapshot_task.get("id"), "status": paper_snapshot_task.get("status")}, ensure_ascii=False), flush=True)
            next_paper_position_snapshot_at = now + max(1, paper_position_snapshot_interval_seconds)
        if next_paper_position_monitor_at is not None and now >= next_paper_position_monitor_at:
            paper_monitor_task = _enqueue_paper_position_monitor(now, paper_position_monitor_interval_seconds)
            print(json.dumps({"scheduled": "paper.positions.monitor", "task_id": paper_monitor_task.get("id"), "status": paper_monitor_task.get("status")}, ensure_ascii=False), flush=True)
            next_paper_position_monitor_at = now + max(1, paper_position_monitor_interval_seconds)
        if next_indicator_precompute_at is not None and now >= next_indicator_precompute_at:
            _enqueue_indicator_precompute(now, indicator_precompute_interval_seconds)
            next_indicator_precompute_at = now + max(1, indicator_precompute_interval_seconds)
        if next_qfq_repair_at is not None and now >= next_qfq_repair_at:
            _enqueue_qfq_repair(now, qfq_repair_interval_seconds)
            next_qfq_repair_at = now + max(1, qfq_repair_interval_seconds)
        if next_strategy_run_at is not None and now >= next_strategy_run_at:
            scheduled = _enqueue_strategy_runs(now, strategy_run_interval_seconds)
            print(json.dumps({"scheduled": "strategy.production_run", **scheduled}, ensure_ascii=False), flush=True)
            next_strategy_run_at = now + max(1, strategy_run_interval_seconds)
        if next_daily_review_at is not None and now >= next_daily_review_at:
            daily_review_task = _enqueue_daily_review(now, daily_review_interval_seconds)
            print(json.dumps({"scheduled": "reports.daily_review", "task_id": daily_review_task.get("id"), "status": daily_review_task.get("status")}, ensure_ascii=False), flush=True)
            next_daily_review_at = now + max(1, daily_review_interval_seconds)
        task = work_once()
        if task:
            processed += 1
            print(json.dumps({"processed": processed, "task_id": task.get("id"), "status": task.get("status")}, ensure_ascii=False), flush=True)
        elif once:
            break
        else:
            time.sleep(max(0.1, poll_seconds))
        if once:
            break
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the 2560 strategy background worker.")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument(
        "--alert-interval-seconds",
        type=int,
        default=int(os.getenv("ALERT_EVALUATION_INTERVAL_SECONDS", "0") or 0),
        help="Schedule alerts.evaluate tasks at this interval; 0 disables periodic alert evaluation.",
    )
    parser.add_argument(
        "--market-sync-interval-seconds",
        type=int,
        default=int(os.getenv("MARKET_SYNC_INTERVAL_SECONDS", "0") or 0),
        help="Schedule market.sync K-line tasks at this interval; 0 disables periodic K-line sync.",
    )
    parser.add_argument(
        "--market-snapshot-interval-seconds",
        type=int,
        default=int(os.getenv("MARKET_SNAPSHOT_INTERVAL_SECONDS", "0") or 0),
        help="Schedule market.snapshot quote tasks at this interval; 0 disables periodic snapshot sync.",
    )
    parser.add_argument(
        "--paper-position-snapshot-interval-seconds",
        type=int,
        default=int(os.getenv("PAPER_POSITION_SNAPSHOT_INTERVAL_SECONDS", "0") or 0),
        help="Schedule quote snapshots for active paper positions at this interval; 0 disables it.",
    )
    parser.add_argument(
        "--paper-position-monitor-interval-seconds",
        type=int,
        default=int(os.getenv("PAPER_POSITION_MONITOR_INTERVAL_SECONDS", "0") or 0),
        help="Schedule active paper position monitor tasks at this interval; 0 disables it.",
    )
    parser.add_argument(
        "--strategy-run-interval-seconds",
        type=int,
        default=int(os.getenv("STRATEGY_RUN_INTERVAL_SECONDS", "0") or 0),
        help="Schedule production runs for deployed strategies at this interval; 0 disables continuous strategy runs.",
    )
    parser.add_argument(
        "--strategy-run-daily-times",
        default=os.getenv("STRATEGY_RUN_DAILY_TIMES", ""),
        help="Comma-separated local wall-clock times such as 14:45 for daily strategy production runs.",
    )
    parser.add_argument(
        "--strategy-run-daily-strategies",
        default=os.getenv("STRATEGY_RUN_DAILY_STRATEGIES", ""),
        help="Comma-separated strategy codes for daily production runs; empty/all means all deployed strategies.",
    )
    parser.add_argument(
        "--strategy-run-daily-grace-seconds",
        type=int,
        default=int(os.getenv("STRATEGY_RUN_DAILY_GRACE_SECONDS", "900") or 900),
        help="How long after a daily scheduled time the worker may still enqueue the daily strategy run.",
    )
    parser.add_argument(
        "--strategy-scan-daily-times",
        default=os.getenv("STRATEGY_SCAN_DAILY_TIMES", ""),
        help="Comma-separated local wall-clock times such as 14:45 for daily scan.run stock selection.",
    )
    parser.add_argument(
        "--strategy-scan-daily-strategies",
        default=os.getenv("STRATEGY_SCAN_DAILY_STRATEGIES", ""),
        help="Comma-separated strategy codes for daily scan.run stock selection.",
    )
    parser.add_argument(
        "--strategy-scan-daily-grace-seconds",
        type=int,
        default=int(os.getenv("STRATEGY_SCAN_DAILY_GRACE_SECONDS", "900") or 900),
        help="How long after a daily scan time the worker may still enqueue the scan.",
    )
    parser.add_argument(
        "--indicator-precompute-interval-seconds",
        type=int,
        default=int(os.getenv("INDICATOR_PRECOMPUTE_INTERVAL_SECONDS", "0") or 0),
        help="Schedule 25/60 local indicator precompute tasks at this interval; 0 disables it.",
    )
    parser.add_argument(
        "--qfq-repair-interval-seconds",
        type=int,
        default=int(os.getenv("QFQ_REPAIR_INTERVAL_SECONDS", "0") or 0),
        help="Schedule qfq correction sync tasks at this interval; 0 disables it.",
    )
    parser.add_argument(
        "--daily-review-interval-seconds",
        type=int,
        default=int(os.getenv("DAILY_REVIEW_INTERVAL_SECONDS", "0") or 0),
        help="Schedule reports.daily_review tasks at this interval; 0 disables daily review automation.",
    )
    parser.add_argument(
        "--bootstrap-on-start",
        action="store_true",
        default=os.getenv("MARKET_BOOTSTRAP_ON_START", "0").strip().lower() in {"1", "true", "yes"},
        help="Queue a full-market history bootstrap before periodic incremental sync starts.",
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    return run_worker(
        poll_seconds=args.poll_seconds,
        once=args.once,
        alert_interval_seconds=args.alert_interval_seconds,
        market_sync_interval_seconds=args.market_sync_interval_seconds,
        market_snapshot_interval_seconds=args.market_snapshot_interval_seconds,
        paper_position_snapshot_interval_seconds=args.paper_position_snapshot_interval_seconds,
        paper_position_monitor_interval_seconds=args.paper_position_monitor_interval_seconds,
        indicator_precompute_interval_seconds=args.indicator_precompute_interval_seconds,
        qfq_repair_interval_seconds=args.qfq_repair_interval_seconds,
        strategy_run_interval_seconds=args.strategy_run_interval_seconds,
        strategy_run_daily_times=args.strategy_run_daily_times,
        strategy_run_daily_strategies=args.strategy_run_daily_strategies,
        strategy_run_daily_grace_seconds=args.strategy_run_daily_grace_seconds,
        strategy_scan_daily_times=args.strategy_scan_daily_times,
        strategy_scan_daily_strategies=args.strategy_scan_daily_strategies,
        strategy_scan_daily_grace_seconds=args.strategy_scan_daily_grace_seconds,
        daily_review_interval_seconds=args.daily_review_interval_seconds,
        bootstrap_on_start=args.bootstrap_on_start,
    )


if __name__ == "__main__":
    raise SystemExit(main())
