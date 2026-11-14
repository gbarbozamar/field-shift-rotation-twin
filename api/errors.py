"""One error shape for every non-2xx response of every route.

    { "error": { "code": "...", "message": "...", "details": [...] } }

Status: PROPOSED (blueprint section 3.7): the closed list of codes, the
message templates and the rule that classifies validation errors.

``message`` is fixed English text for developers. The interface shows its own
strings keyed by ``code``. No response ever echoes the submitted input or the
text of an exception.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.ports import ErrorDetail


class ErrorCode(StrEnum):
    """The closed list of error codes."""

    MALFORMED_JSON = "MALFORMED_JSON"
    INVALID_REQUEST = "INVALID_REQUEST"
    SITE_INVALID = "SITE_INVALID"
    ROTATION_INVALID = "ROTATION_INVALID"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"


MESSAGES: Mapping[ErrorCode, str] = {
    ErrorCode.MALFORMED_JSON: "The request body is not valid JSON.",
    ErrorCode.INVALID_REQUEST: "The request does not match the expected shape.",
    ErrorCode.SITE_INVALID: "The site of the request is not valid.",
    ErrorCode.ROTATION_INVALID: "The rotation of the request is not valid.",
    ErrorCode.INTERNAL_ERROR: "The server failed to process the request.",
    ErrorCode.NOT_FOUND: "No route matches this path.",
    ErrorCode.METHOD_NOT_ALLOWED: "This route does not accept this method.",
}

STATUS: Mapping[ErrorCode, int] = {
    ErrorCode.MALFORMED_JSON: 400,
    ErrorCode.INVALID_REQUEST: 422,
    ErrorCode.SITE_INVALID: 422,
    ErrorCode.ROTATION_INVALID: 422,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
}


class ErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    code: str
    message: str


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    details: list[ErrorItem]


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


def error_response(
    code: ErrorCode,
    details: Iterable[ErrorDetail] = (),
    headers: Mapping[str, str] | None = None,
    status_code: int | None = None,
) -> JSONResponse:
    """Build the one error shape, with the message (and by default the status) of ``code``."""
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=MESSAGES[code],
            details=[
                ErrorItem(path=d.path, code=d.code, message=d.message) for d in details
            ],
        )
    )
    return JSONResponse(
        status_code=status_code if status_code is not None else STATUS[code],
        content=body.model_dump(mode="json"),
        headers=dict(headers) if headers else None,
    )


def join_path(parts: Sequence[Any]) -> str:
    """Dotted path from a location tuple: ``("site", "latitude")`` -> ``site.latitude``."""
    return ".".join(str(part) for part in parts)


def classify_validation_errors(errors: Sequence[Mapping[str, Any]]) -> ErrorCode:
    """Pick the code of a list of request validation errors.

    PROPOSED rule, on locations without the leading ``body``:

    - any ``json_invalid`` error: ``MALFORMED_JSON``;
    - every error lies inside ``site``: ``SITE_INVALID``;
    - every error lies inside ``rotation``: ``ROTATION_INVALID``;
    - otherwise ``INVALID_REQUEST``.

    An error lies inside a field when its location starts with that field and
    it is not that field missing: a missing ``site`` or ``rotation`` is a
    problem of the envelope.
    """
    if any(e.get("type") == "json_invalid" for e in errors):
        return ErrorCode.MALFORMED_JSON
    if not errors:
        return ErrorCode.INVALID_REQUEST
    owners = {_owner(_body_loc(e.get("loc", ())), e.get("type")) for e in errors}
    if owners == {"site"}:
        return ErrorCode.SITE_INVALID
    if owners == {"rotation"}:
        return ErrorCode.ROTATION_INVALID
    return ErrorCode.INVALID_REQUEST


def validation_details(errors: Sequence[Mapping[str, Any]]) -> list[ErrorDetail]:
    """Path, code and message of each error. ``input``, ``ctx`` and ``url`` are dropped."""
    return [
        ErrorDetail(
            path=join_path(_body_loc(e.get("loc", ()))),
            code=str(e.get("type", "")),
            message=str(e.get("msg", "")),
        )
        for e in errors
    ]


def _body_loc(loc: Sequence[Any]) -> tuple[Any, ...]:
    loc = tuple(loc)
    return loc[1:] if loc and loc[0] == "body" else loc


def _owner(loc: tuple[Any, ...], error_type: Any) -> str:
    if not loc:
        return "envelope"
    head = loc[0]
    if head in ("site", "rotation") and (len(loc) > 1 or error_type != "missing"):
        return str(head)
    return "envelope"


def install_error_handlers(app: FastAPI) -> None:
    """Route request validation errors and HTTP exceptions to the one shape.

    Unexpected exceptions are not handled here: each route catches them
    itself, so the CORS middleware still adds its headers to the 500.
    """

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = list(exc.errors())
        code = classify_validation_errors(errors)
        details = [] if code is ErrorCode.MALFORMED_JSON else validation_details(errors)
        return error_response(code, details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = _code_of_status(exc.status_code)
        return error_response(code, (), exc.headers, status_code=exc.status_code)


def _code_of_status(status: int) -> ErrorCode:
    if status == 404:
        return ErrorCode.NOT_FOUND
    if status == 405:
        return ErrorCode.METHOD_NOT_ALLOWED
    if status == 400:
        return ErrorCode.MALFORMED_JSON
    if status >= 500:
        return ErrorCode.INTERNAL_ERROR
    return ErrorCode.INVALID_REQUEST
