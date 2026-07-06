"""FastAPI application factory: middleware, exception handlers, lifespan."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .catalog import UNSUPPORTED_MESSAGE, supported_query_types_payload
from .config import settings
from .db.session import init_db
from .errors import AgentError, UnsupportedQueryError, UpstreamError
from .observability.logging import configure_logging, get_logger
from .observability.tracing import configure_tracing


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    configure_tracing()
    log = get_logger("startup")
    try:
        await init_db()
        log.info("db.ready")
    except Exception as exc:  # don't block boot (e.g. docs) if DB is unavailable
        log.warning("db.init_failed", error=str(exc))
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ClinicalTrials.gov Query-to-Visualization Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(UnsupportedQueryError)
    async def _unsupported(request: Request, exc: UnsupportedQueryError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "unsupported_query",
                "message": exc.reason or UNSUPPORTED_MESSAGE,
                "supported_query_types": supported_query_types_payload(),
                "event_id": exc.event_id,
            },
        )

    @app.exception_handler(UpstreamError)
    async def _upstream(request: Request, exc: UpstreamError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_error", "message": exc.message},
        )

    @app.exception_handler(AgentError)
    async def _agent(request: Request, exc: AgentError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "agent_error", "message": exc.message},
        )

    app.include_router(router)
    return app


app = create_app()
