"""Guards for legacy SQLite maintenance scripts."""

from __future__ import annotations

import os


def _production_like() -> bool:
    return any(
        (os.getenv(name) or "").strip().lower() in {"prod", "production"}
        for name in ("APP_ENV", "FLASK_ENV")
    )


def refuse_production(script_name: str) -> None:
    if _production_like():
        raise SystemExit(
            f"{script_name} is a legacy SQLite maintenance script and is disabled in production. "
            "Use MySQL-backed APIs or migration tooling instead."
        )
