"""Consistent API response helpers."""

from __future__ import annotations

from typing import Any

from flask import jsonify


SUCCESS_CODE = 0


def success(data: Any = None, message: str = "ok", status_code: int = 200):
    payload = {
        "code": SUCCESS_CODE,
        "message": message,
        "data": data if data is not None else {},
    }
    return jsonify(payload), status_code


def error(message: str, code: int = 400, status_code: int = 400, data: Any = None):
    payload = {
        "code": code,
        "message": message,
        "data": data if data is not None else {},
    }
    return jsonify(payload), status_code


def page(items: list[dict], total: int, page_no: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page_no,
        "page_size": page_size,
    }
