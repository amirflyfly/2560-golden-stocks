"""Application errors and Flask error registration."""

from __future__ import annotations

from .responses import error


class AppError(Exception):
    status_code = 400
    code = 400

    def __init__(self, message: str, code: int | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class UnauthorizedError(AppError):
    status_code = 401
    code = 401


class ForbiddenError(AppError):
    status_code = 403
    code = 403


class NotFoundError(AppError):
    status_code = 404
    code = 404


class TenantRequiredError(AppError):
    status_code = 400
    code = 10400


class TenantForbiddenError(AppError):
    status_code = 403
    code = 10403


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError):
        return error(exc.message, code=exc.code, status_code=exc.status_code)

    return app
