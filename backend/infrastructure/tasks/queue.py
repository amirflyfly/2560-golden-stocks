"""Task queue abstraction backed by threads and Redis-compatible state storage."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import traceback
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Callable
from uuid import uuid4

from backend.core.config import get_settings
from backend.infrastructure.cache.redis_client import get_json, pop_value, push_priority_value, push_value, set_json, set_json_if_absent

TaskCallable = Callable[..., dict]

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="strategy-task")
_TASK_INDEX_KEY = "tasks:index"
_TASK_QUEUE_KEY = "tasks:queue"
_TASK_TTL_SECONDS = 86400
_TASK_EVENT_LIMIT = 1000
_STALE_AFTER_SECONDS = 900
_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "stale"}
_CURRENT_TASK_ID: ContextVar[str | None] = ContextVar("current_task_id", default=None)
_MARKET_TASK_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _task_key(task_id: str) -> str:
    return f"tasks:{task_id}"


def _task_idempotency_key(idempotency_key: str) -> str:
    return f"tasks:idempotency:{idempotency_key}"


def _make_idempotency_key(name: str, tenant_id: int | None, payload: dict | None) -> str:
    raw = json.dumps({"name": name, "tenant_id": tenant_id, "payload": payload or {}}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _event(status: str, message: str = "") -> dict:
    return {"status": status, "message": message, "at": _now()}


def current_task_id() -> str | None:
    return _CURRENT_TASK_ID.get()


def append_task_event(task_id: str | None, message: str, *, status: str | None = None, progress: dict | None = None, detail: dict | None = None) -> dict | None:
    if not task_id:
        return None
    task = get_task(task_id)
    if not task:
        return None
    event = _event(status or task.get("status") or "running", message)
    if detail:
        event["detail"] = detail
    events = [*(task.get("events") or []), event]
    task["events"] = events[-_TASK_EVENT_LIMIT:]
    task["heartbeat_at"] = _now()
    if progress is not None:
        result = task.get("result") if isinstance(task.get("result"), dict) else {}
        task["result"] = {**result, "progress": progress}
    task["duration_seconds"] = _duration_seconds(task)
    save_task(task)
    return task


def append_current_task_event(message: str, *, status: str | None = None, progress: dict | None = None, detail: dict | None = None) -> dict | None:
    return append_task_event(current_task_id(), message, status=status, progress=progress, detail=detail)


def _duration_seconds(task: dict) -> float | None:
    started_at = task.get("started_at")
    finished_at = task.get("finished_at")
    if not started_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(finished_at) if finished_at else datetime.now()
        return round((end - start).total_seconds(), 3)
    except (TypeError, ValueError):
        return None


def _failure_category(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "connection" in name or "redis" in name:
        return "infrastructure"
    if "value" in name or "validation" in name:
        return "validation"
    return "unexpected"


def _requires_serial_lane(task: dict) -> bool:
    name = str(task.get("name") or "")
    return name.startswith("market.")


def _execute_task_unlocked(task_id: str, func: TaskCallable, *args: Any, **kwargs: Any) -> dict | None:
    current = get_task(task_id)
    if not current:
        return None
    if current.get("status") == "cancelled":
        current["finished_at"] = current.get("finished_at") or _now()
        current["duration_seconds"] = _duration_seconds(current)
        current.setdefault("events", []).append(_event("cancelled", "cancelled before start"))
        save_task(current)
        return current
    current.update({"status": "running", "started_at": current.get("started_at") or _now(), "heartbeat_at": _now()})
    current.setdefault("events", []).append(_event("running", "worker started"))
    save_task(current)
    while True:
        try:
            current["heartbeat_at"] = _now()
            save_task(current)
            token = _CURRENT_TASK_ID.set(task_id)
            try:
                result = func(*args, **kwargs)
            finally:
                _CURRENT_TASK_ID.reset(token)
            latest = get_task(task_id) or current
            if latest.get("status") == "cancelled":
                latest.update({"finished_at": latest.get("finished_at") or _now(), "duration_seconds": _duration_seconds(latest)})
                latest.setdefault("events", []).append(_event("cancelled", "cancelled while running"))
                current = latest
            else:
                current = latest
                current.update(
                    {
                        "status": "completed",
                        "result": result,
                        "finished_at": _now(),
                        "heartbeat_at": _now(),
                        "error": None,
                        "failure_category": None,
                    }
                )
                current["duration_seconds"] = _duration_seconds(current)
                current.setdefault("events", []).append(_event("completed", "task completed"))
            break
        except Exception as exc:  # pragma: no cover - defensive background path
            latest = get_task(task_id) or current
            if latest.get("status") == "cancelled":
                current = latest
                current.update({"finished_at": current.get("finished_at") or _now(), "duration_seconds": _duration_seconds(current)})
                current.setdefault("events", []).append(_event("cancelled", "cancelled while failing"))
                break
            current = latest
            category = _failure_category(exc)
            retry_count = int(current.get("retry_count") or 0)
            max_retry_count = int(current.get("max_retries") or 0)
            if retry_count < max_retry_count:
                current.update(
                    {
                        "status": "retrying",
                        "retry_count": retry_count + 1,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        "failure_category": category,
                        "heartbeat_at": _now(),
                    }
                )
                current.setdefault("events", []).append(_event("retrying", f"retry {retry_count + 1}/{max_retry_count}"))
                save_task(current)
                current.update({"status": "running", "heartbeat_at": _now()})
                current.setdefault("events", []).append(_event("running", "retry worker started"))
                save_task(current)
                continue
            current.update(
                {
                    "status": "failed",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "failure_category": category,
                    "finished_at": _now(),
                    "heartbeat_at": _now(),
                }
            )
            current["duration_seconds"] = _duration_seconds(current)
            error_summary = str(exc).strip()[:300] or category
            current.setdefault("events", []).append(_event("failed", f"任务失败：{error_summary}"))
            break
    save_task(current)
    return current


def _load_index() -> list[str]:
    data = get_json(_TASK_INDEX_KEY) or {"ids": []}
    return list(data.get("ids", []))


def _save_index(task_ids: list[str]):
    set_json(_TASK_INDEX_KEY, {"ids": task_ids[:200]}, ttl_seconds=_TASK_TTL_SECONDS)


def _active_task_for_idempotency_key(idempotency_key: str) -> dict | None:
    item = get_json(_task_idempotency_key(idempotency_key)) or {}
    task_id = item.get("task_id")
    task = get_task(task_id) if task_id else None
    if task and task.get("status") not in _TERMINAL_STATUSES:
        return task
    return None


def save_task(task: dict):
    set_json(_task_key(task["id"]), task, ttl_seconds=_TASK_TTL_SECONDS)
    task_ids = [task["id"], *[item for item in _load_index() if item != task["id"]]]
    _save_index(task_ids)


def get_task(task_id: str) -> dict | None:
    return get_json(_task_key(task_id))


def list_tasks(limit: int = 20, *, name: str | None = None, status: str | None = None) -> list[dict]:
    items = []
    normalized_name = (name or "").strip() or None
    normalized_status = (status or "").strip() or None
    for task_id in _load_index()[: max(limit * 3, limit, 20)]:
        task = get_task(task_id)
        if not task:
            continue
        if normalized_name and task.get("name") != normalized_name:
            continue
        if normalized_status and task.get("status") != normalized_status:
            continue
        items.append(task)
        if len(items) >= limit:
            break
    return items


def update_task(task_id: str, updates: dict) -> dict | None:
    task = get_task(task_id)
    if not task:
        return None
    previous_status = task.get("status")
    task.update(updates)
    if task.get("status") != previous_status:
        task.setdefault("events", []).append(_event(task.get("status") or "updated", "manual update"))
    task["duration_seconds"] = _duration_seconds(task)
    save_task(task)
    return task


def mark_stale_tasks(stale_after_seconds: int = _STALE_AFTER_SECONDS) -> list[dict]:
    marked = []
    threshold = datetime.now() - timedelta(seconds=max(1, int(stale_after_seconds)))
    for task_id in _load_index():
        task = get_task(task_id)
        if not task or task.get("status") != "running":
            continue
        heartbeat_at = task.get("heartbeat_at") or task.get("started_at")
        try:
            heartbeat = datetime.fromisoformat(heartbeat_at)
        except (TypeError, ValueError):
            heartbeat = threshold - timedelta(seconds=1)
        if heartbeat < threshold:
            task.update(
                {
                    "status": "stale",
                    "finished_at": task.get("finished_at") or _now(),
                    "error": task.get("error") or "task heartbeat expired",
                    "failure_category": "stale",
                    "duration_seconds": _duration_seconds(task),
                }
            )
            task.setdefault("events", []).append(_event("stale", "heartbeat expired"))
            save_task(task)
            marked.append(task)
    return marked


def dequeue_task_id() -> str | None:
    return pop_value(_TASK_QUEUE_KEY)


def _execute_task(task_id: str, func: TaskCallable, *args: Any, **kwargs: Any) -> dict | None:
    current = get_task(task_id)
    if not current:
        return None
    if not _requires_serial_lane(current):
        return _execute_task_unlocked(task_id, func, *args, **kwargs)

    acquired = _MARKET_TASK_LOCK.acquire(blocking=False)
    if not acquired:
        current.setdefault("events", []).append(_event("pending", "waiting for market task lane"))
        save_task(current)
        _MARKET_TASK_LOCK.acquire()
    try:
        return _execute_task_unlocked(task_id, func, *args, **kwargs)
    finally:
        _MARKET_TASK_LOCK.release()


def run_queued_task(task_id: str, func: TaskCallable, *args: Any, **kwargs: Any) -> dict | None:
    return _execute_task(task_id, func, *args, **kwargs)


def enqueue_task(
    name: str,
    func: TaskCallable,
    *args: Any,
    tenant_id: int | None = None,
    payload: dict | None = None,
    idempotency_key: str | None = None,
    max_retries: int = 0,
    priority: bool = False,
    **kwargs: Any,
) -> dict:
    normalized_payload = payload or {}
    normalized_idempotency_key = idempotency_key or _make_idempotency_key(name, tenant_id, normalized_payload)
    existing = _active_task_for_idempotency_key(normalized_idempotency_key)
    if existing:
        return existing

    settings = get_settings()
    task = {
        "id": uuid4().hex,
        "name": name,
        "tenant_id": tenant_id,
        "status": "pending",
        "payload": normalized_payload,
        "idempotency_key": normalized_idempotency_key,
        "queue_backend": settings.task_queue_backend,
        "execution_mode": settings.task_execution_mode,
        "priority": bool(priority),
        "retry_count": 0,
        "max_retries": max(0, int(max_retries or 0)),
        "failure_category": None,
        "heartbeat_at": None,
        "duration_seconds": None,
        "events": [_event("queued", "task accepted")],
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }
    if not set_json_if_absent(
        _task_idempotency_key(normalized_idempotency_key),
        {"task_id": task["id"], "created_at": task["created_at"]},
        ttl_seconds=_TASK_TTL_SECONDS,
    ):
        existing = _active_task_for_idempotency_key(normalized_idempotency_key)
        if existing:
            return existing
        set_json(
            _task_idempotency_key(normalized_idempotency_key),
            {"task_id": task["id"], "created_at": task["created_at"]},
            ttl_seconds=_TASK_TTL_SECONDS,
        )
    save_task(task)

    if settings.task_execution_mode == "worker":
        if priority:
            push_priority_value(_TASK_QUEUE_KEY, task["id"])
        else:
            push_value(_TASK_QUEUE_KEY, task["id"])
        return task

    if os.getenv("PYTEST_CURRENT_TEST") and name in {
        "scan.run",
        "scan.strategy",
        "market.sync",
        "market.sync.plan",
        "market.snapshot",
        "market.snapshot.plan",
        "market.indicators.precompute",
        "market.qfq.repair",
        "strategy.production_run",
        "reports.daily_review",
    }:
        _execute_task(task["id"], func, *args, **kwargs)
        return get_task(task["id"]) or task

    def runner():
        _execute_task(task["id"], func, *args, **kwargs)

    _executor.submit(runner)
    return task
