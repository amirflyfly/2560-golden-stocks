"""Application service for strategy API endpoints."""

from __future__ import annotations

from backend.application.pagination import PaginationParams


DEFAULT_STRATEGIES = [
    {
        "id": 1,
        "code": "2560",
        "name": "2560 战法",
        "category": "趋势策略",
        "description": "围绕 25 日均线、60 日均量和趋势延续做候选筛选。",
        "enabled": True,
    },
    {
        "id": 2,
        "code": "first_limit_up",
        "name": "首板涨停",
        "category": "打板策略",
        "description": "识别首板涨停后的次日预期和跟踪机会。",
        "enabled": True,
    },
]


class StrategyApiService:
    def list_strategies(self, tenant_id: int, pagination: PaginationParams) -> dict:
        items = DEFAULT_STRATEGIES[pagination.offset : pagination.offset + pagination.page_size]
        return {
            "items": items,
            "total": len(DEFAULT_STRATEGIES),
            "page": pagination.page,
            "page_size": pagination.page_size,
            "tenant_id": tenant_id,
        }

    def get_strategy(self, tenant_id: int, strategy_id: int) -> dict | None:
        for strategy in DEFAULT_STRATEGIES:
            if strategy["id"] == strategy_id:
                return {**strategy, "tenant_id": tenant_id}
        return None
