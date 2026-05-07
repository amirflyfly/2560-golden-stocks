from __future__ import annotations

import sys
import time
import types

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


def test_worker_daily_review_handler_calls_report_service(monkeypatch):
    from backend.application import report_api_service
    from backend.infrastructure.tasks import handlers

    calls = []

    class FakeReportService:
        def daily_review(self, tenant_id, trade_date=None, *, account_id=None, push=False, channels=None, user_id=None, source="api"):
            calls.append(
                {
                    "tenant_id": tenant_id,
                    "trade_date": trade_date,
                    "account_id": account_id,
                    "push": push,
                    "channels": channels,
                    "user_id": user_id,
                    "source": source,
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

    worker._enqueue_daily_review(1000.0, 60)

    assert enqueued[0]["name"] == "reports.daily_review"
    assert enqueued[0]["tenant_id"] == 8
    assert enqueued[0]["payload"]["trade_date"] == "2026-05-06"
    assert enqueued[0]["payload"]["push"] is True
    assert enqueued[0]["payload"]["channels"] == ["webhook", "email"]
    assert enqueued[0]["payload"]["account_id"] == 3
    assert enqueued[0]["payload"]["user_id"] == 5
    assert "reports.daily_review:8:2026-05-06" in enqueued[0]["idempotency_key"]
