"""Registration helpers for the v1 API."""

from __future__ import annotations

from flask import Flask

from backend.api_v1.blueprint import api_v1_bp
from backend.core.errors import register_error_handlers


def register_api_v1(app: Flask) -> Flask:
    register_error_handlers(app)
    if "api_v1" not in app.blueprints:
        app.register_blueprint(api_v1_bp)
    return app
