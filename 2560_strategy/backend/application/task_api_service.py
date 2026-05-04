"""Application service for task status APIs."""

from __future__ import annotations

from backend.application.pagination import PaginationParams
from backend.infrastructure.cache.redis_client import cache_health
from datetime import datetime

from backend.infrastructure.tasks.queue import get_task, list_tasks, mark_stale_tasks, update_task

STATUS_ALIASES = {
    "queued": "pending",
    "succeeded": "completed",
    "canceled": "cancelled",
}
LIFECYCLE_STATUS = {
    "pending": "queued",
    "completed": "succeeded",
    "cancelled": "canceled",
}
SORT_FIELDS = {
    "created_at",
    "started_at",
    "finished_at",
    "duration_seconds",
    "status",
    "lifecycle_status",
    "name",
    "failure_category",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_task_status(status: str | None) -> str | None:
    normalized = (status or "").strip().lower()
    if not normalized:
        return None
    return STATUS_ALIASES.get(normalized, normalized)


def task_lifecycle_status(status: str | None) -> str:
    normalized = (status or "").strip().lower()
    return LIFECYCLE_STATUS.get(normalized, normalized or "unknown")


class TaskApiService:
    def list_tasks(
        self,
        tenant_id: int,
        pagination: PaginationParams,
        *,
        name: str | None = None,
        status: str | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> dict:
        mark_stale_tasks()
        normalized_status = normalize_task_status(status)
        filtered_items = [
            self._present_task(item)
            for item in list_tasks(limit=200, name=name, status=normalized_status)
            if item.get("tenant_id") == tenant_id
        ]
        sort_field = self._normalize_sort(sort)
        sort_order = "asc" if (order or "").strip().lower() == "asc" else "desc"
        filtered_items = self._sort_items(filtered_items, sort_field, sort_order)
        start = pagination.offset
        end = start + pagination.page_size
        return {
            "items": filtered_items[start:end],
            "total": len(filtered_items),
            "page": pagination.page,
            "page_size": pagination.page_size,
            "tenant_id": tenant_id,
            "filters": {"name": name or "", "status": status or "", "normalized_status": normalized_status or ""},
            "sort": {"field": sort_field, "order": sort_order},
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
            "lifecycle_status": task_lifecycle_status(task.get("status")),
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

    def _normalize_sort(self, sort: str | None) -> str:
        normalized = (sort or "created_at").strip().lower()
        return normalized if normalized in SORT_FIELDS else "created_at"

    def _sort_items(self, items: list[dict], sort_field: str, sort_order: str) -> list[dict]:
        reverse = sort_order != "asc"

        def key(item: dict):
            value = item.get(sort_field)
            if value is None:
                return (1, "")
            return (0, value)

        return sorted(items, key=key, reverse=reverse)
