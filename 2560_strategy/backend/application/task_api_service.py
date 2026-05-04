"""Application service for task status APIs."""

from __future__ import annotations

from backend.application.pagination import PaginationParams
from backend.infrastructure.cache.redis_client import cache_health
from datetime import datetime

from backend.infrastructure.tasks.queue import get_task, list_tasks, mark_stale_tasks, update_task


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TaskApiService:
    def list_tasks(
        self,
        tenant_id: int,
        pagination: PaginationParams,
        *,
        name: str | None = None,
        status: str | None = None,
    ) -> dict:
        mark_stale_tasks()
        filtered_items = [
            self._present_task(item)
            for item in list_tasks(limit=200, name=name, status=status)
            if item.get("tenant_id") == tenant_id
        ]
        start = pagination.offset
        end = start + pagination.page_size
        return {
            "items": filtered_items[start:end],
            "total": len(filtered_items),
            "page": pagination.page,
            "page_size": pagination.page_size,
            "tenant_id": tenant_id,
            "filters": {"name": name or "", "status": status or ""},
            "cache": cache_health().to_dict(),
        }

    def get_task(self, tenant_id: int, task_id: str) -> dict | None:
        task = get_task(task_id)
        if not task or task.get("tenant_id") != tenant_id:
            return None
        return self._present_task(task)

    def cancel_task(self, tenant_id: int, task_id: str) -> dict | None:
        task = get_task(task_id)
        if not task or task.get("tenant_id") != tenant_id:
            return None
        if task.get("status") in {"completed", "failed", "cancelled"}:
            return self._present_task(task)
        task = update_task(
            task_id,
            {
                "status": "cancelled",
                "finished_at": task.get("finished_at") or _now(),
                "error": "task marked as cancelled; running worker threads cannot be force-stopped",
                "failure_category": "cancelled",
            },
        )
        return self._present_task(task or {})

    def _present_task(self, task: dict) -> dict:
        result = task.get("result") or {}
        error = task.get("error")
        return {
            **task,
            "duration_seconds": task.get("duration_seconds") if task.get("duration_seconds") is not None else self._duration_seconds(task),
            "error_summary": str(error)[:300] if error else None,
            "result_summary": self._result_summary(result),
            "events": task.get("events") or [],
            "failure_category": task.get("failure_category"),
            "retry_count": task.get("retry_count", 0),
            "max_retries": task.get("max_retries", 0),
            "idempotency_key": task.get("idempotency_key"),
            "heartbeat_at": task.get("heartbeat_at"),
        }

    def _duration_seconds(self, task: dict) -> float | None:
        from datetime import datetime

        started_at = task.get("started_at")
        finished_at = task.get("finished_at")
        if not started_at:
            return None
        try:
            start = datetime.fromisoformat(started_at)
            end = datetime.fromisoformat(finished_at) if finished_at else datetime.now()
            return round((end - start).total_seconds(), 3)
        except ValueError:
            return None

    def _result_summary(self, result: dict) -> dict:
        if not isinstance(result, dict):
            return {}
        market_data = result.get("market_data") or {}
        return {
            "matched_count": result.get("matched_count"),
            "provider": market_data.get("provider"),
            "healthy": market_data.get("healthy"),
        }
