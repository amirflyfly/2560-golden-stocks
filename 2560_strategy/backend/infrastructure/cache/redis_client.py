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
        self._lists: dict[str, list[str]] = {}

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and self.get(key) is not None:
            return False
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

    def lpush(self, key: str, value: str):
        self._lists.setdefault(key, []).insert(0, value)
        return len(self._lists[key])

    def rpop(self, key: str):
        values = self._lists.get(key) or []
        if not values:
            return None
        return values.pop()


_client: Any | None = None
_fallback_client = InMemoryRedisLike()


def get_redis_client():
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    if settings.cache_backend == "memory":
        _client = _fallback_client
        return _client
    try:
        import redis  # type: ignore

        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        _client.ping()
        return _client
    except Exception as exc:
        if settings.cache_backend == "redis" or (settings.environment or "").strip().lower() in {"prod", "production"}:
            raise RuntimeError("Redis cache backend is required but unavailable") from exc
        _client = _fallback_client
        return _client


def cache_health() -> CacheHealth:
    try:
        client = get_redis_client()
        client.ping()
        backend = "memory" if isinstance(client, InMemoryRedisLike) else "redis"
        return CacheHealth(backend=backend, ok=True)
    except Exception as exc:
        return CacheHealth(backend="redis", ok=False, message=str(exc))


def set_json(key: str, value: dict, ttl_seconds: int | None = None):
    get_redis_client().set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)


def set_json_if_absent(key: str, value: dict, ttl_seconds: int | None = None) -> bool:
    payload = json.dumps(value, ensure_ascii=False)
    client = get_redis_client()
    try:
        return bool(client.set(key, payload, ex=ttl_seconds, nx=True))
    except TypeError:  # pragma: no cover - compatibility for minimal Redis-like clients
        if client.get(key) is not None:
            return False
        client.set(key, payload, ex=ttl_seconds)
        return True


def get_json(key: str) -> dict | None:
    raw = get_redis_client().get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def push_value(key: str, value: str) -> None:
    get_redis_client().lpush(key, value)


def pop_value(key: str) -> str | None:
    raw = get_redis_client().rpop(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)
