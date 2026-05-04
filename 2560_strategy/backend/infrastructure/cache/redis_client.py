"""Redis client adapter with an in-memory fallback for local development and tests."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from backend.core.config import get_settings


@dataclass
class CacheHealth:
    backend: str
    ok: bool
    message: str = "ok"

    def to_dict(self) -> dict:
        return {"backend": self.backend, "ok": self.ok, "message": self.message}


class InMemoryRedisLike:
    def __init__(self):
        self._values: dict[str, tuple[str, float | None]] = {}

    def set(self, key: str, value: str, ex: int | None = None):
        expires_at = time.time() + ex if ex else None
        self._values[key] = (value, expires_at)
        return True

    def get(self, key: str):
        item = self._values.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at and expires_at < time.time():
            self._values.pop(key, None)
            return None
        return value

    def ping(self):
        return True


_client: Any | None = None
_fallback_client = InMemoryRedisLike()


def get_redis_client():
    global _client
    if _client is not None:
        return _client
    try:
        import redis  # type: ignore

        _client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        _client.ping()
        return _client
    except Exception:
        _client = _fallback_client
        return _client


def cache_health() -> CacheHealth:
    client = get_redis_client()
    try:
        client.ping()
        backend = "memory" if isinstance(client, InMemoryRedisLike) else "redis"
        return CacheHealth(backend=backend, ok=True)
    except Exception as exc:
        return CacheHealth(backend="redis", ok=False, message=str(exc))


def set_json(key: str, value: dict, ttl_seconds: int | None = None):
    get_redis_client().set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)


def get_json(key: str) -> dict | None:
    raw = get_redis_client().get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)
