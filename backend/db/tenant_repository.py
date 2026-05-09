"""Tenant-scoped repository helpers.

These helpers provide a single place for tenant filters so business queries do
not accidentally read or write data across tenants.
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.db.mixins import TenantScopedMixin

ModelT = TypeVar("ModelT", bound=TenantScopedMixin)


class TenantScopedRepository:
    def __init__(self, session: Session, model: type[ModelT], tenant_id: int):
        self.session = session
        self.model = model
        self.tenant_id = tenant_id

    def base_query(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    def get(self, item_id: int) -> ModelT | None:
        stmt = self.base_query().where(self.model.id == item_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        stmt = self.base_query().limit(limit).offset(offset)
        return list(self.session.execute(stmt).scalars().all())

    def add(self, values: dict[str, Any]) -> ModelT:
        values = dict(values)
        values["tenant_id"] = self.tenant_id
        item = self.model(**values)
        self.session.add(item)
        return item

    def filter_by(self, **filters: Any) -> list[ModelT]:
        stmt = self.base_query()
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        return list(self.session.execute(stmt).scalars().all())
