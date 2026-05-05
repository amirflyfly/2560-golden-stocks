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
