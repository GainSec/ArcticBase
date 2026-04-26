"""RFC 7807-style problem responses for storage-layer exceptions."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from arctic_base.storage.errors import (
    AlreadyExists,
    InvalidTheme,
    NotFound,
    StaleETag,
)


def _problem(status: int, title: str, detail: str, type_: str = "about:blank") -> JSONResponse:
    return JSONResponse(
        {"type": type_, "title": title, "status": status, "detail": detail},
        status_code=status,
        media_type="application/problem+json",
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound) -> JSONResponse:
        return _problem(404, "Not Found", str(exc))

    @app.exception_handler(AlreadyExists)
    async def already_exists(_: Request, exc: AlreadyExists) -> JSONResponse:
        return _problem(409, "Conflict", str(exc))

    @app.exception_handler(StaleETag)
    async def stale_etag(_: Request, exc: StaleETag) -> JSONResponse:
        return _problem(412, "Precondition Failed", str(exc))

    @app.exception_handler(InvalidTheme)
    async def invalid_theme(_: Request, exc: InvalidTheme) -> JSONResponse:
        return _problem(422, "Unprocessable Entity", str(exc))

    @app.exception_handler(ValueError)
    async def bad_request(_: Request, exc: ValueError) -> JSONResponse:
        return _problem(400, "Bad Request", str(exc))
