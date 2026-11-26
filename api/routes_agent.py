"""Agent 接口：工具清单 + 一次带工具调用的对话。

规划失败/工具参数错误都由 ToolError 收敛，再翻成 AppError，返回统一的
{"error": {code, message, request_id, details}} 结构。
"""
from __future__ import annotations

from fastapi import APIRouter

from tools.registry import ToolError

from .errors import AppError
from .schemas import (
    AgentChatRequest,
    AgentChatResponse,
    Citation,
    ErrorResponse,
    ToolCallTrace,
    ToolSpec,
)

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "空消息 / 非法 URL / 未知工具"},
    422: {"model": ErrorResponse, "description": "工具参数不合法"},
    502: {"model": ErrorResponse, "description": "工具执行失败（抓取失败等）"},
    503: {"model": ErrorResponse, "description": "索引或校历未就绪"},
}


def build_agent_router(get_agent):
    router = APIRouter(prefix="/agent", tags=["agent"])

    def agent_or_fail():
        agent = get_agent()
        if agent is None:
            raise AppError("INTERNAL_ERROR", "Agent 未初始化")
        return agent

    @router.get("/tools", response_model=list[ToolSpec], summary="列出可用工具及其参数 schema")
    def list_tools() -> list[ToolSpec]:
        return [ToolSpec(**spec) for spec in agent_or_fail().registry.specs()]

    @router.post(
        "/chat",
        response_model=AgentChatResponse,
        responses=ERROR_RESPONSES,
        summary="发一条消息，由 Agent 选择工具并回答（带多轮记忆）",
    )
    def chat(payload: AgentChatRequest) -> AgentChatResponse:
        try:
            result = agent_or_fail().chat(
                payload.message, session_id=payload.session_id, max_steps=payload.max_steps
            )
        except ToolError as exc:
            raise AppError(exc.code, exc.message, details=exc.details) from exc
        return AgentChatResponse(
            session_id=result["session_id"],
            message=result["message"],
            answer=result["answer"],
            tool_calls=[ToolCallTrace(**item) for item in result["tool_calls"]],
            citations=[Citation(**item) for item in result["citations"]],
            used_tools=result["used_tools"],
            planner=result["planner"],
            steps_used=result["steps_used"],
            latency_ms=result["latency_ms"],
        )

    return router
