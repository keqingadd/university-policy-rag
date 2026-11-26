"""请求/响应模型。

question 的长度校验故意不放在 Pydantic 里：空问题和超长问题要返回业务错误码
（EMPTY_QUESTION / QUESTION_TOO_LONG），而 Pydantic 的类型/范围错误统一归为
INVALID_PARAM。两者在接口测试里是不同断言。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["hybrid", "bm25", "vector"]


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., description="用户问题，去除首尾空白后 1~2000 字")
    top_k: int | None = Field(None, ge=1, le=10, description="召回条数，缺省用服务端配置")
    mode: Mode | None = Field(None, description="检索模式，缺省用服务端配置")


class ContextItem(BaseModel):
    id: int
    doc_id: str
    title: str
    chunk_index: int
    score: float
    snippet: str


class QueryResponse(BaseModel):
    question: str
    answer: str
    contexts: list[ContextItem]
    latency_ms: float
    used_llm: bool
    mode: str
    top_k: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    chunks: int
    embedder: str
    version: str
    index_dir: str
    detail: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
