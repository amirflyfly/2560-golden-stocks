from __future__ import annotations

import sys
import threading
import time
import types
from datetime import datetime

import pytest

from backend.core.config import get_settings
from backend.infrastructure.cache import redis_client
from backend.infrastructure.tasks import queue


@pytest.fixture(autouse=True)
def clear_cached_settings():
    get_settings.cache_clear()
    redis_client._client = None
    yield
    get_settings.cache_clear()
    redis_client._client = None


def _reset_memory_backend(monkeypatch, *, execution_mode: str = "worker"):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CACHE_BACKEND", "memory")
    monkeypatch.setenv("TASK_QUEUE_BACKEND", "memory")
    monkeypatch.setenv("TASK_EXECUTION_MODE", execution_mode)
    get_settings.cache_clear()
    redis_client._client = redis_client.InMemoryRedisLike()


def test_enqueue_task_deduplicates_active_idempotency_key(monkeypatch):
    _reset_memory_backend(monkeypatch, execution_mode="worker")

    first = queue.enqueue_task("unit.example", lambda: {"ok": True}, tenant_id=7, payload={"symbol": "000001"})
    second = queue.enqueue_task("unit.example", lambda: {"ok": True}, tenant_id=7, payload={"symbol": "000001"})

    assert second["id"] == first["id"]
    assert second["status"] == "pending"
    assert queue.dequeue_task_id() == first["id"]


def test_priority_task_dequeues_before_existing_worker_backlog(monkeypatch):
    _reset_memory_backend(monkeypatch, execution_mode="worker")

    normal = queue.enqueue_task("unit.normal", lambda: {"ok": True}, tenant_id=1, payload={"order": 1})
    priority = queue.enqueue_task("unit.priority", lambda: {"ok": True}, tenant_id=1, payload={"order": 2}, priority=True)

    assert priority["priority"] is True
    assert queue.dequeue_task_id() == priority["id"]
    assert queue.dequeue_task_id() == normal["id"]


def test_worker_mode_queues_and_run_queued_task_executes(monkeypatch):
    _reset_memory_backend(monkeypatch, execution_mode="worker")

    task = queue.enqueue_task("unit.run", lambda: {"ignored": True}, tenant_id=1, payload={"x": 1})
    queued_id = queue.dequeue_task_id()

    assert queued_id == task["id"]

    result = queue.run_queued_task(queued_id, lambda: {"ok": True})

    assert result is not None
    assert result["status"] == "completed"
    assert result["result"] == {"ok": True}


def test_threadpool_mode_runs_without_worker_queue(monkeypatch):
    _reset_memory_backend(monkeypatch, execution_mode="threadpool")

    task = queue.enqueue_task("unit.threadpool", lambda: {"ok": True}, tenant_id=1, payload={"x": 2})

    assert queue.dequeue_task_id() is None
    assert task["execution_mode"] == "threadpool"
    for _ in range(20):
        saved = queue.get_task(task["id"])
        if saved and saved.get("status") == "completed":
            break
        time.sleep(0.05)
    assert queue.get_task(task["id"])["status"] == "completed"


def test_threadpool_market_tasks_run_in_serial_lane(monkeypatch):
    _reset_memory_backend(monkeypatch, execution_mode="threadpool")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    active = 0
    max_active = 0
    active_lock = threading.Lock()

    def slow_task(label):
        nonlocal active, max_active
        with active_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.12)
        with active_lock:
            active -= 1
        return {"label": label}

    tasks = [
        queue.enqueue_task("market.sync", slow_task, label, tenant_id=1, payload={"label": label})
        for label in ("a", "b", "c")
    ]
    deadline = time.time() + 5
    while time.time() < deadline:
        saved = [queue.get_task(task["id"]) for task in tasks]
        if all(item and item.get("status") == "completed" for item in saved):
            break
        time.sleep(0.03)

    assert [queue.get_task(task["id"])["status"] for task in tasks] == ["completed", "completed", "completed"]
    assert max_active == 1


def test_production_redis_cache_does_not_fallback_to_memory(monkeypatch):
    class FailingRedisClient:
        def ping(self):
            raise ConnectionError("redis unavailable")

    class FailingRedis:
        @staticmethod
        def from_url(_url, decode_responses=True):
            return FailingRedisClient()

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "0")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://strategy:strong-password@mysql:3306/strategy_2560")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "mootdx")
    monkeypatch.setenv("MARKET_DATA_FALLBACKS", "akshare")
    monkeypatch.setenv("CACHE_BACKEND", "redis")
    monkeypatch.setenv("TASK_QUEUE_BACKEND", "redis")
    monkeypatch.setenv("TASK_EXECUTION_MODE", "worker")
    monkeypatch.setitem(sys.modules, "redis", types.SimpleNamespace(Redis=FailingRedis))
    get_settings.cache_clear()
    redis_client._client = None

    with pytest.raises(RuntimeError, match="Redis cache backend is required"):
        redis_client.get_redis_client()


def test_worker_handlers_preserve_market_sync_contract(monkeypatch):
    from backend.application import sync_api_service
    from backend.infrastructure.tasks import handlers

    calls = []

    class FakeSyncService:
        def _sync_market_data(
            self,
            symbols,
            start_date,
            end_date,
            adjust,
            max_symbols,
            tenant_id,
            incremental,
            bootstrap_days,
            correction_days,
            interval="1d",
            security_type=None,
        ):
            calls.append(
                {
                    "method": "sync",
                    "symbols": symbols,
                    "adjust": adjust,
                    "max_symbols": max_symbols,
                    "tenant_id": tenant_id,
                    "incremental": incremental,
                    "bootstrap_days": bootstrap_days,
                    "correction_days": correction_days,
                    "interval": interval,
                    "security_type": security_type,
                }
            )
            return {"ok": True}

        def _plan_market_sync(
            self,
            tenant_id,
            symbols,
            start_date,
            end_date,
            adjust,
            max_symbols=0,
            batch_size=200,
            incremental=False,
            bootstrap_days=180,
            correction_days=3,
            interval="1d",
            security_type=None,
        ):
            calls.append(
                {
                    "method": "plan",
                    "symbols": symbols,
                    "adjust": adjust,
                    "max_symbols": max_symbols,
                    "batch_size": batch_size,
                    "tenant_id": tenant_id,
                    "incremental": incremental,
                    "bootstrap_days": bootstrap_days,
                    "correction_days": correction_days,
                    "interval": interval,
                    "security_type": security_type,
                }
            )
            return {"ok": True}

    monkeypatch.setattr(sync_api_service, "SyncApiService", FakeSyncService)
    payload = {
        "symbols": "all",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "adjust": "none",
        "interval": "15m",
        "security_type": "convertible_bond",
        "max_symbols": 50,
        "batch_size": 10,
        "incremental": True,
        "bootstrap_days": 30,
        "correction_days": 2,
    }

    handlers.get_task_handler("market.sync")({"tenant_id": 3, "payload": payload})
    handlers.get_task_handler("market.sync.plan")({"tenant_id": 3, "payload": payload})

    assert calls == [
        {
            "method": "sync",
            "symbols": "all",
            "adjust": "none",
            "max_symbols": 50,
            "tenant_id": 3,
            "incremental": True,
            "bootstrap_days": 30,
            "correction_days": 2,
            "interval": "15m",
            "security_type": "convertible_bond",
        },
        {
            "method": "plan",
            "symbols": "all",
            "adjust": "none",
            "max_symbols": 50,
            "batch_size": 10,
            "tenant_id": 3,
            "incremental": True,
            "bootstrap_days": 30,
            "correction_days": 2,
            "interval": "15m",
            "security_type": "convertible_bond",
        },
    ]


def test_worker_handlers_preserve_snapshot_security_type(monkeypatch):
    from backend.application import sync_api_service
    from backend.infrastructure.tasks import handlers

    calls = []

    class FakeSyncService:
        def _sync_quote_snapshots(self, symbols, max_symbols=0, security_type=None):
            calls.append(("snapshot", symbols, max_symbols, security_type))
            return {"ok": True}

        def _plan_quote_snapshot_sync(self, tenant_id, symbols, max_symbols=0, batch_size=500, security_type=None):
            calls.append(("snapshot_plan", tenant_id, symbols, max_symbols, batch_size, security_type))
            return {"ok": True}

    monkeypatch.setattr(sync_api_service, "SyncApiService", FakeSyncService)
    payload = {"symbols": "all", "max_symbols": 40, "batch_size": 8, "security_type": "stock"}

    handlers.get_task_handler("market.snapshot")({"tenant_id": 4, "payload": payload})
    handlers.get_task_handler("market.snapshot.plan")({"tenant_id": 4, "payload": payload})

    assert calls == [
        ("snapshot", "all", 40, "stock"),
        ("snapshot_plan", 4, "all", 40, 8, "stock"),
    ]


def test_worker_handler_runs_auction_snapshot_sync(monkeypatch):
    from backend.application import sync_api_service
    from backend.infrastructure.tasks import handlers

    calls = []

    class FakeSyncService:
        def _sync_auction_snapshots(self, symbols, trade_date=None, max_symbols=0, security_type="stock", force=False):
            calls.append((symbols, trade_date, max_symbols, security_type, force))
            return {"status": "completed"}

    monkeypatch.setattr(sync_api_service, "SyncApiService", FakeSyncService)

    result = handlers.get_task_handler("market.auction.sync")(
        {
            "tenant_id": 4,
            "payload": {
                "symbols": "all",
                "trade_date": "2026-05-06",
                "max_symbols": 20,
                "security_type": "stock",
                "force": True,
            },
        }
    )

    assert result["status"] == "completed"
    assert calls == [("all", "2026-05-06", 20, "stock", True)]


def test_worker_scheduled_market_tasks_include_interval_and_security_type(monkeypatch):
    from backend.infrastructure.tasks import worker

    enqueued = []

    def fake_enqueue_task(name, func, *args, tenant_id=None, payload=None, idempotency_key=None, max_retries=0):
        enqueued.append(
            {
                "name": name,
                "tenant_id": tenant_id,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "max_retries": max_retries,
            }
        )
        return {"id": f"task-{len(enqueued)}", "status": "pending"}

    monkeypatch.setattr(worker, "enqueue_task", fake_enqueue_task)
    monkeypatch.setenv("WORKER_TENANT_ID", "9")
    monkeypatch.setenv("MARKET_SYNC_SYMBOLS", "all")
    monkeypatch.setenv("MARKET_SYNC_INTERVAL", "15m")
    monkeypatch.setenv("MARKET_SYNC_SECURITY_TYPE", "convertible_bond")
    monkeypatch.setenv("MARKET_SYNC_BATCH_SIZE", "25")
    monkeypatch.setenv("MARKET_SNAPSHOT_BATCH_SIZE", "30")

    worker._enqueue_market_sync(1000.0, 60)
    worker._enqueue_market_snapshot(1000.0, 30)

    assert enqueued[0]["name"] == "market.sync.plan"
    assert enqueued[0]["tenant_id"] == 9
    assert enqueued[0]["payload"]["interval"] == "15m"
    assert enqueued[0]["payload"]["security_type"] == "convertible_bond"
    assert "15m" in enqueued[0]["idempotency_key"]
    assert "convertible_bond" in enqueued[0]["idempotency_key"]
    assert enqueued[1]["name"] == "market.snapshot.plan"
    assert enqueued[1]["payload"]["security_type"] == "convertible_bond"


def test_worker_scheduled_paper_position_snapshot_task_uses_env(monkeypatch):
    from backend.infrastructure.tasks import worker

    enqueued = []

    def fake_enqueue_task(name, func, *args, tenant_id=None, payload=None, idempotency_key=None, max_retries=0, priority=False):
        enqueued.append(
            {
                "name": name,
                "tenant_id": tenant_id,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "max_retries": max_retries,
                "priority": priority,
            }
        )
        return {"id": "paper-position-snapshot-task", "status": "pending"}

    monkeypatch.setattr(worker, "enqueue_task", fake_enqueue_task)
    monkeypatch.setenv("WORKER_TENANT_ID", "9")
    monkeypatch.setenv("PAPER_POSITION_SNAPSHOT_ACCOUNT_ID", "12")
    monkeypatch.setenv("PAPER_POSITION_SNAPSHOT_MAX_SYMBOLS", "88")
    monkeypatch.setenv("PAPER_POSITION_SNAPSHOT_BATCH_SIZE", "22")
    monkeypatch.setenv("PAPER_POSITION_SNAPSHOT_SECURITY_TYPE", "stock")

    worker._enqueue_paper_position_snapshot(1000.0, 20)

    assert enqueued == [
        {
            "name": "paper.positions.snapshot",
            "tenant_id": 9,
            "payload": {
                "account_id": 12,
                "max_symbols": 88,
                "batch_size": 22,
                "security_type": "stock",
                "source": "worker-paper-position-scheduler",
                "scheduled_bucket": 50,
                "skip_reason": "",
            },
            "idempotency_key": "paper.positions.snapshot:9:12:50:88:22:stock",
            "max_retries": 1,
            "priority": True,
        }
    ]


def test_worker_scheduled_paper_position_monitor_task_uses_env(monkeypatch):
    from backend.infrastructure.tasks import worker

    enqueued = []

    def fake_enqueue_task(name, func, *args, tenant_id=None, payload=None, idempotency_key=None, max_retries=0, priority=False):
        enqueued.append(
            {
                "name": name,
                "tenant_id": tenant_id,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "max_retries": max_retries,
                "priority": priority,
            }
        )
        return {"id": "paper-position-monitor-task", "status": "pending"}

    monkeypatch.setattr(worker, "enqueue_task", fake_enqueue_task)
    monkeypatch.setenv("WORKER_TENANT_ID", "9")
    monkeypatch.setenv("PAPER_POSITION_MONITOR_ACCOUNT_ID", "12")
    monkeypatch.setenv("PAPER_POSITION_MONITOR_MAX_SYMBOLS", "88")
    monkeypatch.setenv("PAPER_POSITION_MONITOR_BATCH_SIZE", "22")
    monkeypatch.setenv("PAPER_POSITION_MONITOR_SECURITY_TYPE", "stock")
    monkeypatch.setenv("PAPER_POSITION_MONITOR_SYNC_SNAPSHOTS", "1")
    monkeypatch.setenv("PAPER_POSITION_MONITOR_EVALUATE_EXITS", "1")

    worker._enqueue_paper_position_monitor(1000.0, 20)

    assert enqueued == [
        {
            "name": "paper.positions.monitor",
            "tenant_id": 9,
            "payload": {
                "account_id": 12,
                "max_symbols": 88,
                "batch_size": 22,
                "security_type": "stock",
                "sync_snapshots": True,
                "evaluate_exits": True,
                "source": "worker-paper-position-monitor",
                "scheduled_bucket": 50,
                "skip_reason": "",
            },
            "idempotency_key": "paper.positions.monitor:9:12:50:88:22:stock:True:True",
            "max_retries": 1,
            "priority": True,
        }
    ]


def test_paper_position_snapshot_service_queues_existing_snapshot_task(monkeypatch):
    from backend.application import sync_api_service

    enqueued = []

    monkeypatch.setattr(
        sync_api_service.paper_trading_repo,
        "list_active_position_symbols",
        lambda tenant_id, account_id=None, limit=0: ["000001", "600519"],
    )

    def fake_enqueue_task(name, func, *args, tenant_id=None, payload=None, idempotency_key=None, max_retries=0, priority=False):
        enqueued.append(
            {
                "name": name,
                "args": args,
                "tenant_id": tenant_id,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "max_retries": max_retries,
                "priority": priority,
            }
        )
        return {"id": "snapshot-child", "name": name, "status": "pending"}

    monkeypatch.setattr(sync_api_service, "enqueue_task", fake_enqueue_task)

    result = sync_api_service.SyncApiService(market_data_provider=object()).enqueue_paper_position_snapshot_sync(
        3,
        {
            "account_id": 7,
            "max_symbols": 20,
            "batch_size": 10,
            "security_type": "stock",
            "source": "worker-paper-position-scheduler",
            "scheduled_bucket": 123,
        },
    )

    assert result["status"] == "queued"
    assert result["symbol_count"] == 2
    assert result["updated_at"]
    assert result["snapshot_task"] == {"id": "snapshot-child", "name": "market.snapshot.plan", "status": "pending"}
    assert enqueued[0]["name"] == "market.snapshot.plan"
    assert enqueued[0]["tenant_id"] == 3
    assert enqueued[0]["payload"]["symbols"] == ["000001", "600519"]
    assert enqueued[0]["payload"]["symbol_count"] == 2
    assert enqueued[0]["payload"]["paper_position_symbol_count"] == 2
    assert enqueued[0]["payload"]["updated_at"]
    assert enqueued[0]["payload"]["skip_reason"] == ""
    assert enqueued[0]["payload"]["parent"] == "paper.positions.snapshot"
    assert enqueued[0]["priority"] is True


def test_paper_position_snapshot_service_skips_without_active_positions(monkeypatch):
    from backend.application import sync_api_service

    monkeypatch.setattr(
        sync_api_service.paper_trading_repo,
        "list_active_position_symbols",
        lambda tenant_id, account_id=None, limit=0: [],
    )

    def fail_enqueue(*_args, **_kwargs):
        raise AssertionError("snapshot task should not be queued")

    monkeypatch.setattr(sync_api_service, "enqueue_task", fail_enqueue)

    result = sync_api_service.SyncApiService(market_data_provider=object()).enqueue_paper_position_snapshot_sync(
        3,
        {"account_id": 7, "scheduled_bucket": 123},
    )

    assert result["status"] == "skipped"
    assert result["skip_reason"] == "no_active_paper_positions"
    assert result["symbol_count"] == 0
    assert result["updated_at"]


def test_paper_position_monitor_syncs_prices_and_evaluates_exits(monkeypatch):
    from backend.application import paper_trading_service, sync_api_service

    positions = [
        {"account_id": 7, "symbol": "000001", "quantity": 100, "security_type": "stock"},
        {"account_id": 8, "symbol": "600519", "quantity": 100, "security_type": "stock"},
    ]
    snapshot_calls = []
    persisted = []
    mark_calls = []
    exit_calls = []

    class FakeProvider:
        name = "fake"

        def get_quote_snapshots(self, symbols):
            snapshot_calls.append(list(symbols))
            return [{"symbol": symbol, "last_price": 10.0, "source": "fake"} for symbol in symbols]

    class FakePaperTradingService:
        def mark_to_market(self, tenant_id, account_id=None, payload=None):
            mark_calls.append((tenant_id, account_id, payload))
            return {"updated": 1, "missing": [], "stale": []}

        def evaluate_exits(self, tenant_id, account_id, payload=None):
            exit_calls.append((tenant_id, account_id, payload))
            return {"orders": [{"id": account_id}], "skipped": [], "blocked": []}

    monkeypatch.setattr(sync_api_service.paper_trading_repo, "list_positions", lambda tenant_id, account_id=None, active_only=False: positions)
    monkeypatch.setattr(sync_api_service.market_data_repo, "upsert_quote_snapshots", lambda snapshots: persisted.append(list(snapshots)) or len(snapshots))
    monkeypatch.setattr(sync_api_service.market_data_repo, "snapshot_summary", lambda *args, **kwargs: {"snapshot_count": sum(len(item) for item in persisted)})
    monkeypatch.setattr(paper_trading_service, "PaperTradingService", FakePaperTradingService)

    result = sync_api_service.SyncApiService(FakeProvider()).monitor_paper_positions(
        3,
        {"batch_size": 1, "source": "unit-monitor", "scheduled_bucket": 123},
    )

    assert result["schema_version"] == "paper-position-monitor/v1"
    assert result["status"] == "completed"
    assert result["symbol_count"] == 2
    assert snapshot_calls == [["000001"], ["600519"]]
    assert result["snapshot_sync"]["persisted_snapshots"] == 2
    assert [item["account_id"] for item in result["accounts"]] == [7, 8]
    assert result["exit_summary"] == {"orders": 2, "skipped": 0, "blocked": 0}
    assert [call[1] for call in mark_calls] == [7, 8]
    assert [call[1] for call in exit_calls] == [7, 8]


def test_paper_position_monitor_skips_without_active_positions(monkeypatch):
    from backend.application import sync_api_service

    monkeypatch.setattr(sync_api_service.paper_trading_repo, "list_positions", lambda tenant_id, account_id=None, active_only=False: [])

    result = sync_api_service.SyncApiService(market_data_provider=object()).monitor_paper_positions(
        3,
        {"account_id": 7, "scheduled_bucket": 123},
    )

    assert result["status"] == "skipped"
    assert result["skip_reason"] == "no_active_paper_positions"
    assert result["symbol_count"] == 0
    assert result["updated_at"]


def test_worker_handler_runs_paper_position_snapshot_service(monkeypatch):
    from backend.application import sync_api_service
    from backend.infrastructure.tasks import handlers

    calls = []

    class FakeSyncService:
        def enqueue_paper_position_snapshot_sync(self, tenant_id, payload):
            calls.append((tenant_id, payload))
            return {"status": "skipped", "skip_reason": "no_active_paper_positions", "symbol_count": 0}

    monkeypatch.setattr(sync_api_service, "SyncApiService", FakeSyncService)

    result = handlers.get_task_handler("paper.positions.snapshot")(
        {"tenant_id": 6, "payload": {"scheduled_bucket": 10}}
    )

    assert result["status"] == "skipped"
    assert result["skip_reason"] == "no_active_paper_positions"
    assert calls == [(6, {"scheduled_bucket": 10})]


def test_worker_handler_runs_paper_position_monitor_service(monkeypatch):
    from backend.application import sync_api_service
    from backend.infrastructure.tasks import handlers

    calls = []

    class FakeSyncService:
        def monitor_paper_positions(self, tenant_id, payload):
            calls.append((tenant_id, payload))
            return {"status": "skipped", "skip_reason": "no_active_paper_positions", "symbol_count": 0}

    monkeypatch.setattr(sync_api_service, "SyncApiService", FakeSyncService)

    result = handlers.get_task_handler("paper.positions.monitor")(
        {"tenant_id": 6, "payload": {"scheduled_bucket": 10}}
    )

    assert result["status"] == "skipped"
    assert result["skip_reason"] == "no_active_paper_positions"
    assert calls == [(6, {"scheduled_bucket": 10})]


def test_worker_daily_review_handler_calls_report_service(monkeypatch):
    from backend.application import report_api_service
    from backend.infrastructure.tasks import handlers

    calls = []

    class FakeReportService:
        def daily_review(self, tenant_id, trade_date=None, *, account_id=None, push=False, channels=None, user_id=None, source="api", evaluate_exits=False):
            calls.append(
                {
                    "tenant_id": tenant_id,
                    "trade_date": trade_date,
                    "account_id": account_id,
                    "push": push,
                    "channels": channels,
                    "user_id": user_id,
                    "source": source,
                    "evaluate_exits": evaluate_exits,
                }
            )
            return {"schema_version": "daily-review/v1"}

    monkeypatch.setattr(report_api_service, "ReportApiService", FakeReportService)

    result = handlers.get_task_handler("reports.daily_review")(
        {
            "tenant_id": 6,
            "payload": {
                "trade_date": "2026-05-06",
                "account_id": 2,
                "push": True,
                "channels": ["webhook"],
                "user_id": 9,
                "source": "worker-scheduler",
                "evaluate_exits": True,
            },
        }
    )

    assert result["schema_version"] == "daily-review/v1"
    assert calls == [
        {
            "tenant_id": 6,
            "trade_date": "2026-05-06",
            "account_id": 2,
            "push": True,
            "channels": ["webhook"],
            "user_id": 9,
            "source": "worker-scheduler",
            "evaluate_exits": True,
        }
    ]


def test_worker_scheduled_daily_review_task_includes_push_contract(monkeypatch):
    from backend.infrastructure.tasks import worker

    enqueued = []

    def fake_enqueue_task(name, func, *args, tenant_id=None, payload=None, idempotency_key=None, max_retries=0):
        enqueued.append(
            {
                "name": name,
                "tenant_id": tenant_id,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "max_retries": max_retries,
            }
        )
        return {"id": "daily-review-task", "status": "pending"}

    monkeypatch.setattr(worker, "enqueue_task", fake_enqueue_task)
    monkeypatch.setenv("WORKER_TENANT_ID", "8")
    monkeypatch.setenv("DAILY_REVIEW_TRADE_DATE", "2026-05-06")
    monkeypatch.setenv("DAILY_REVIEW_PUSH", "1")
    monkeypatch.setenv("DAILY_REVIEW_CHANNELS", "webhook,email")
    monkeypatch.setenv("DAILY_REVIEW_ACCOUNT_ID", "3")
    monkeypatch.setenv("DAILY_REVIEW_USER_ID", "5")
    monkeypatch.setenv("DAILY_REVIEW_EVALUATE_EXITS", "1")

    worker._enqueue_daily_review(1000.0, 60)

    assert enqueued[0]["name"] == "reports.daily_review"
    assert enqueued[0]["tenant_id"] == 8
    assert enqueued[0]["payload"]["trade_date"] == "2026-05-06"
    assert enqueued[0]["payload"]["push"] is True
    assert enqueued[0]["payload"]["channels"] == ["webhook", "email"]
    assert enqueued[0]["payload"]["account_id"] == 3
    assert enqueued[0]["payload"]["user_id"] == 5
    assert enqueued[0]["payload"]["evaluate_exits"] is True
    assert "reports.daily_review:8:2026-05-06" in enqueued[0]["idempotency_key"]


def test_worker_daily_strategy_time_bucket_uses_local_wall_clock():
    from backend.infrastructure.tasks import worker

    daily_times = worker._parse_daily_times("14:45")
    due = worker._due_daily_time_buckets(datetime(2026, 5, 13, 14, 45, 30).timestamp(), daily_times, 900)
    late = worker._due_daily_time_buckets(datetime(2026, 5, 13, 15, 1, 0).timestamp(), daily_times, 900)

    assert due == [("2026-05-13T14:45", "14:45")]
    assert late == []


def test_worker_daily_strategy_run_filters_limit_up_return_and_2560(monkeypatch):
    from backend.infrastructure.tasks import worker
    from backend.repositories import strategy_repo

    enqueued = []

    def fake_list_strategies(active_only=True):
        return [
            {"id": 1, "code": "LIMIT_UP_RETURN", "enabled": True, "lifecycle_status": "deployed"},
            {"id": 2, "code": "2560", "enabled": True, "lifecycle_status": "deployed"},
            {"id": 3, "code": "first_limit_up", "enabled": True, "lifecycle_status": "deployed"},
        ]

    def fake_enqueue_task(name, func, *args, tenant_id=None, payload=None, idempotency_key=None, max_retries=0):
        enqueued.append(
            {
                "name": name,
                "tenant_id": tenant_id,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "max_retries": max_retries,
            }
        )
        return {"id": f"strategy-task-{len(enqueued)}", "status": "pending"}

    monkeypatch.setattr(strategy_repo, "list_strategies", fake_list_strategies)
    monkeypatch.setattr(worker, "list_tasks", lambda *args, **kwargs: [])
    monkeypatch.setattr(worker, "enqueue_task", fake_enqueue_task)
    monkeypatch.setenv("WORKER_TENANT_ID", "8")
    monkeypatch.setenv("STRATEGY_RUN_SCAN_LIMIT", "6000")

    result = worker._enqueue_strategy_runs(
        datetime(2026, 5, 13, 14, 45).timestamp(),
        86400,
        strategy_codes="涨停回马枪,25-60",
        source="worker-daily-scheduler",
        scheduled_bucket="2026-05-13T14:45",
        skip_existing=True,
    )

    assert result["scheduled_strategies"] == 2
    assert [item["payload"]["strategy_code"] for item in enqueued] == ["LIMIT_UP_RETURN", "2560"]
    assert [item["payload"]["params"]["source"] for item in enqueued] == ["worker-daily-scheduler", "worker-daily-scheduler"]
    assert [item["payload"]["params"]["scheduled_bucket"] for item in enqueued] == ["2026-05-13T14:45", "2026-05-13T14:45"]
    assert all("strategy.production_run:2026-05-13T14:45:8:" in item["idempotency_key"] for item in enqueued)


def test_worker_daily_strategy_scan_queues_scan_run_for_selection(monkeypatch):
    from backend.infrastructure.tasks import worker

    enqueued = []

    def fake_enqueue_task(name, func, *args, tenant_id=None, payload=None, idempotency_key=None, max_retries=0):
        enqueued.append(
            {
                "name": name,
                "tenant_id": tenant_id,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "max_retries": max_retries,
            }
        )
        return {"id": f"scan-task-{len(enqueued)}", "status": "pending"}

    monkeypatch.setattr(worker, "list_tasks", lambda *args, **kwargs: [])
    monkeypatch.setattr(worker, "enqueue_task", fake_enqueue_task)
    monkeypatch.setenv("WORKER_TENANT_ID", "8")
    monkeypatch.setenv("STRATEGY_SCAN_DAILY_SCAN_LIMIT", "6000")

    result = worker._enqueue_strategy_scans(
        datetime(2026, 5, 13, 14, 45).timestamp(),
        strategy_codes="涨停回马枪,25-60",
        source="worker-daily-scan-scheduler",
        scheduled_bucket="2026-05-13T14:45",
        skip_existing=True,
    )

    assert result["scheduled_scans"] == 2
    assert [item["name"] for item in enqueued] == ["scan.run", "scan.run"]
    assert [item["payload"]["strategy_code_internal"] for item in enqueued] == ["2560", "LIMIT_UP_RETURN"]
    assert [item["payload"]["params"]["source"] for item in enqueued] == ["worker-daily-scan-scheduler", "worker-daily-scan-scheduler"]
    assert [item["payload"]["params"]["scheduled_bucket"] for item in enqueued] == ["2026-05-13T14:45", "2026-05-13T14:45"]
    assert all(item["payload"]["params"]["disable_market_sample_fallback"] is True for item in enqueued)
    assert all("scan.run.daily:2026-05-13T14:45:8:" in item["idempotency_key"] for item in enqueued)
