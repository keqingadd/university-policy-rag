"""FastAPI 入口：uvicorn api.main:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import VERSION, load_settings
from .errors import AppError
from .schemas import (
    ContextItem,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
)
from .service import RagService

logger = logging.getLogger("rag.api")

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "空问题 / 超长问题"},
    422: {"model": ErrorResponse, "description": "参数不合法"},
    500: {"model": ErrorResponse, "description": "服务内部错误"},
    503: {"model": ErrorResponse, "description": "索引未就绪"},
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _error_response(request: Request, exc: AppError) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=exc.code,
            message=exc.message,
            request_id=_request_id(request),
            details=exc.details,
        )
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = load_settings()
        app.state.settings = settings
        try:
            app.state.service = RagService.from_dir(settings.index_dir, settings)
            logger.info(
                "index loaded: dir=%s chunks=%d embedder=%s",
                settings.index_dir,
                len(app.state.service.index.chunks),
                app.state.service.index.embedder_name,
            )
        except AppError as exc:
            app.state.service = None
            app.state.load_error = exc
            logger.error("index not ready: %s", exc.message)
        yield

    app = FastAPI(
        title="高校学生政策问答助手 API",
        description="对 university-policy-rag 的 HTTP 封装：BM25 + 向量混合检索，带引用溯源。",
        version=VERSION,
        lifespan=lifespan,
        responses=ERROR_RESPONSES,
    )
    app.state.service = None
    app.state.load_error = None

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        cost_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Process-Time-Ms"] = f"{cost_ms:.1f}"
        logger.info(
            "%s %s -> %s %.1fms rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            cost_ms,
            request.state.request_id,
        )
        return response

    @app.exception_handler(AppError)
    async def on_app_error(request: Request, exc: AppError):
        logger.warning("app error %s: %s rid=%s", exc.code, exc.message, _request_id(request))
        return _error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError):
        fields = [
            {
                "loc": ".".join(str(part) for part in item.get("loc", ())),
                "msg": item.get("msg", ""),
                "type": item.get("type", ""),
            }
            for item in exc.errors()
        ]
        return _error_response(
            request,
            AppError("INVALID_PARAM", "请求参数不合法", details={"fields": fields}),
        )

    @app.exception_handler(Exception)
    async def on_unexpected_error(request: Request, exc: Exception):
        logger.exception("unhandled error rid=%s", _request_id(request))
        return _error_response(request, AppError("INTERNAL_ERROR", "服务内部错误"))

    def require_service() -> RagService:
        service = app.state.service
        if service is None:
            raise app.state.load_error or AppError("INDEX_NOT_READY")
        return service

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    def health() -> JSONResponse | HealthResponse:
        service = app.state.service
        if service is None:
            payload = HealthResponse(
                status="degraded",
                chunks=0,
                embedder="unknown",
                version=VERSION,
                index_dir=str(getattr(app.state, "settings", load_settings()).index_dir),
                detail=str(getattr(app.state.load_error, "message", "索引未加载")),
            )
            return JSONResponse(status_code=503, content=payload.model_dump())
        return HealthResponse(**service.health())

    @app.post("/query", response_model=QueryResponse, tags=["qa"])
    def query(payload: QueryRequest, request: Request) -> QueryResponse:
        service = require_service()
        result = service.ask(payload.question, payload.top_k, payload.mode)
        logger.info(
            "query ok chars=%d top_k=%d mode=%s latency_ms=%s rid=%s",
            len(result["question"]),
            result["top_k"],
            result["mode"],
            result["latency_ms"],
            _request_id(request),
        )
        return QueryResponse(
            question=result["question"],
            answer=result["answer"],
            contexts=[ContextItem(**item) for item in result["contexts"]],
            latency_ms=result["latency_ms"],
            used_llm=result["used_llm"],
            mode=result["mode"],
            top_k=result["top_k"],
        )

    return app


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = create_app()
