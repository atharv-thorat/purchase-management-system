"""Domain errors and their HTTP mapping (D-27, D-37).

Services raise these; `register_error_handlers` turns them into
`{"error": <code>, "message": <human-readable>}` responses the frontend can show as-is.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = 400
    code = "DOMAIN_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details


class Unauthorized(DomainError):
    status_code = 401
    code = "UNAUTHORIZED"


class Forbidden(DomainError):
    """Role or segregation-of-duties violation."""

    status_code = 403
    code = "FORBIDDEN"


class NotFound(DomainError):
    """Missing record, or one outside the caller's read scope (D-37)."""

    status_code = 404
    code = "NOT_FOUND"


class InvalidTransition(DomainError):
    status_code = 409
    code = "INVALID_TRANSITION"


class BusinessRuleViolation(DomainError):
    status_code = 422
    code = "BUSINESS_RULE_VIOLATION"


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": code, "message": message}
    if details is not None:
        body["details"] = details
    return body


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError):
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, Unauthorized) else None
        return JSONResponse(_body(exc.code, exc.message, exc.details), exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"{where}: {first.get('msg')}" if where else str(first.get("msg", "Invalid request"))
        return JSONResponse(_body("VALIDATION_ERROR", message, jsonable_encoder(errors)), 422)
