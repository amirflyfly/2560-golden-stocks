"""Central application settings for the refactored API layer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse


INSECURE_SECRET_KEYS = {
    "",
    "dev-only-change-me",
    "change-me-in-production",
    "your-secret-key-change-in-production",
}
INSECURE_DATABASE_PASSWORDS = {"", "password", "strategy_password", "root"}
PRODUCTION_CACHE_BACKENDS = {"redis"}
PRODUCTION_TASK_QUEUE_BACKENDS = {"redis"}
PRODUCTION_TASK_EXECUTION_MODES = {"worker"}
REPOSITORY_BACKEND_ENV_VARS = (
    "PICKS_REPOSITORY_BACKEND",
    "AUTH_REPOSITORY_BACKEND",
    "AUDIT_REPOSITORY_BACKEND",
    "SETTINGS_REPOSITORY_BACKEND",
    "LOGS_REPOSITORY_BACKEND",
    "STRATEGY_POOL_REPOSITORY_BACKEND",
    "STRATEGY_REPOSITORY_BACKEND",
    "TRADING_REPOSITORY_BACKEND",
)
PRODUCTION_REPOSITORY_BACKENDS = {"", "auto", "mysql"}


def _is_production(environment: str) -> bool:
    return (environment or "").strip().lower() in {"prod", "production"}


def _database_password(database_url: str) -> str:
    parsed = urlparse(database_url or "")
    return parsed.password or ""


def _validate_production_repository_backends() -> None:
    invalid = []
    for name in REPOSITORY_BACKEND_ENV_VARS:
        value = os.getenv(name, "").strip().lower()
        if value not in PRODUCTION_REPOSITORY_BACKENDS:
            invalid.append(f"{name}={value or '<empty>'}")
    if invalid:
        joined = ", ".join(invalid)
        raise RuntimeError(f"Production repository backends must be mysql or auto: {joined}")


def effective_repository_backends(environment: str | None = None) -> dict[str, str]:
    env = environment if environment is not None else os.getenv("APP_ENV", "development")
    defaults_to_mysql = _is_production(env)
    backends: dict[str, str] = {}
    for name in REPOSITORY_BACKEND_ENV_VARS:
        forced = (os.getenv(name) or "auto").strip().lower()
        if forced in {"sqlite", "mysql"}:
            backends[name] = forced
        else:
            backends[name] = "mysql" if defaults_to_mysql else "sqlite"
    return backends


@dataclass(frozen=True)
class Settings:
    app_name: str = "2560 strategy"
    api_prefix: str = "/api/v1"
    environment: str = "development"
    debug: bool = False
    secret_key: str = "dev-only-change-me"
    database_url: str = "mysql+pymysql://root:password@localhost:3306/strategy_2560?charset=utf8mb4"
    redis_url: str = "redis://localhost:6379/0"
    market_data_provider: str = "mock"
    market_data_fallbacks: tuple[str, ...] = ("akshare", "mock")
    allow_mock_market_data: bool = False
    access_token_minutes: int = 60
    cors_allowed_origins: tuple[str, ...] = ()
    log_level: str = "INFO"
    cache_backend: str = "auto"
    task_queue_backend: str = "memory"
    task_execution_mode: str = "threadpool"

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("APP_ENV", "development")
        debug = os.getenv("APP_DEBUG", "0") == "1"
        secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")
        database_url = os.getenv(
            "DATABASE_URL",
            "mysql+pymysql://root:password@localhost:3306/strategy_2560?charset=utf8mb4",
        )
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        market_data_provider = os.getenv("MARKET_DATA_PROVIDER", "mock").lower()
        fallbacks = os.getenv("MARKET_DATA_FALLBACKS", "akshare,mock")
        market_data_fallbacks = tuple(item.strip().lower() for item in fallbacks.split(",") if item.strip())
        allow_mock_market_data = os.getenv("ALLOW_MOCK_MARKET_DATA", "0") == "1"
        cors_allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
        default_log_level = "INFO" if _is_production(environment) else ("DEBUG" if debug else "INFO")
        log_level = os.getenv("LOG_LEVEL", default_log_level).strip().upper() or default_log_level
        cache_backend = os.getenv("CACHE_BACKEND", "redis" if _is_production(environment) else "auto").strip().lower()
        task_queue_backend = os.getenv("TASK_QUEUE_BACKEND", "redis" if _is_production(environment) else "memory").strip().lower()
        task_execution_mode = os.getenv("TASK_EXECUTION_MODE", "worker" if _is_production(environment) else "threadpool").strip().lower()

        if _is_production(environment):
            if debug:
                raise RuntimeError("APP_DEBUG must be 0 in production")
            if secret_key in INSECURE_SECRET_KEYS or len(secret_key) < 32:
                raise RuntimeError("SECRET_KEY must be set to a strong random value in production")
            if not os.getenv("DATABASE_URL"):
                raise RuntimeError("DATABASE_URL must be explicitly set in production")
            if _database_password(database_url) in INSECURE_DATABASE_PASSWORDS:
                raise RuntimeError("DATABASE_URL uses an insecure database password in production")
            if os.getenv("INIT_SQLITE_SCHEMA", "").strip().lower() in {"1", "true", "yes"}:
                raise RuntimeError("INIT_SQLITE_SCHEMA is not allowed in production")
            if not allow_mock_market_data and market_data_provider == "mock":
                raise RuntimeError("MARKET_DATA_PROVIDER=mock is not allowed in production")
            if not allow_mock_market_data and "mock" in market_data_fallbacks:
                raise RuntimeError("MARKET_DATA_FALLBACKS must not include mock in production")
            if cache_backend not in PRODUCTION_CACHE_BACKENDS:
                raise RuntimeError("CACHE_BACKEND must be redis in production")
            if task_queue_backend not in PRODUCTION_TASK_QUEUE_BACKENDS:
                raise RuntimeError("TASK_QUEUE_BACKEND must be redis in production")
            if task_execution_mode not in PRODUCTION_TASK_EXECUTION_MODES:
                raise RuntimeError("TASK_EXECUTION_MODE must be worker in production")
            _validate_production_repository_backends()

        return cls(
            environment=environment,
            debug=debug,
            secret_key=secret_key,
            database_url=database_url,
            redis_url=redis_url,
            market_data_provider=market_data_provider,
            market_data_fallbacks=market_data_fallbacks,
            allow_mock_market_data=allow_mock_market_data,
            access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "60")),
            cors_allowed_origins=tuple(item.strip() for item in cors_allowed_origins.split(",") if item.strip()),
            log_level=log_level,
            cache_backend=cache_backend,
            task_queue_backend=task_queue_backend,
            task_execution_mode=task_execution_mode,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
