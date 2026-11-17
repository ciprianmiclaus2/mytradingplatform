"""Consistent API error responses.

Every error returned by the API has the shape::

    {"error": {"code": "...", "message": "...", "details": ...}}

Stack traces are logged on the backend and never returned to the client.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.persistence.errors import LockTimeoutError, PersistenceError

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """Base class for expected, client-facing application errors."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


def _error(status: int, code: str, message: str, details: Any | None = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def _validation_message(details: list[dict[str, object]]) -> str:
    """A readable summary: the reason a value was rejected, when the model gave one."""
    reasons = [str(d["msg"]).removeprefix("Value error, ") for d in details if d.get("type") == "value_error"]
    return f"Request validation failed: {'; '.join(reasons)}" if reasons else "Request validation failed"


_HTTP_CODES = {404: "not_found", 405: "method_not_allowed", 409: "conflict"}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return _error(422, "validation_error", _validation_message(details), details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(PersistenceError)
    async def _persistence_error(request: Request, exc: PersistenceError) -> JSONResponse:
        logger.error(
            "persistence error",
            exc_info=exc,
            extra={"path": request.url.path, "method": request.method},
        )
        status = 503 if isinstance(exc, LockTimeoutError) else 500
        return _error(status, exc.code, str(exc))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled exception",
            extra={"path": request.url.path, "method": request.method},
        )
        return _error(500, "internal_error", "An unexpected error occurred")
