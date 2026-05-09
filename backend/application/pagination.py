"""Pagination helpers for API services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaginationParams:
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def normalize_pagination(page: int | str | None = None, page_size: int | str | None = None) -> PaginationParams:
    try:
        normalized_page = max(int(page or 1), 1)
    except ValueError:
        normalized_page = 1
    try:
        normalized_page_size = int(page_size or 20)
    except ValueError:
        normalized_page_size = 20
    normalized_page_size = min(max(normalized_page_size, 1), 200)
    return PaginationParams(page=normalized_page, page_size=normalized_page_size)
