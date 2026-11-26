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


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., description="用户消息，去除首尾空白后 1~2000 字")
    session_id: str | None = Field(
        None,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
        description="多轮会话 id，不传则服务端生成",
    )
    max_steps: int | None = Field(None, ge=1, le=3, description="本次最多调用几个工具")


class ToolCallTrace(BaseModel):
    tool: str
    args: dict
    ok: bool
    latency_ms: float
    error: str | None = None
    message: str | None = None
    summary: str | None = None


class Citation(BaseModel):
    id: int
    doc_id: str
    title: str
    snippet: str


class AgentChatResponse(BaseModel):
    session_id: str
    message: str
    answer: str
    tool_calls: list[ToolCallTrace]
    citations: list[Citation]
    used_tools: list[str]
    planner: str
    steps_used: int
    latency_ms: float


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
