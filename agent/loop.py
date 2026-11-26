"""Agent 执行循环：规划 -> 调工具 -> 组织答案 -> 写多轮记忆。"""
from __future__ import annotations

import time
import uuid

from tools.registry import ToolError, ToolRegistry

from .memory import SessionMemory
from .planner import plan


def _calendar_sentence(data: dict) -> str:
    parts = [f"{data['date']}（{data.get('weekday', '')}）"]
    if data.get("teaching_week"):
        parts.append(f"第 {data['teaching_week']} 教学周")
    term = data.get("term") or {}
    if term.get("name"):
        parts.append(f"学期：{term['name']}")
    if data.get("current_event"):
        parts.append(f"当前处于「{data['current_event']['name']}」")
    elif data.get("in_break"):
        parts.append("当前在假期中")
    elif data.get("in_term") is False:
        parts.append("当前不在学期内")
    if data.get("next_event"):
        event = data["next_event"]
        parts.append(f"下一个节点「{event['name']}」{event['start']} 开始，还有 {event['days_until']} 天")
    if data.get("upcoming_60d"):
        names = "、".join(f"{item['name']}({item['start']})" for item in data["upcoming_60d"][:3])
        parts.append(f"60 天内还有：{names}")
    return "；".join(parts) + "。"


def _web_sentence(data: dict) -> str:
    head = f"已抓取 {data['url']}（HTTP {data['status']}）"
    if data.get("title"):
        head += f"，标题《{data['title']}》"
    body = " ".join((data.get("text") or "").split())
    head += "。正文节选：" + body[:300] + ("…" if len(body) > 300 else "")
    return head


def _digest(tool: str, data: dict) -> str:
    if tool == "policy_search":
        return f"{data.get('n_contexts', 0)} 条切片，mode={data.get('mode')}"
    if tool == "calendar":
        week = data.get("teaching_week")
        return f"{data.get('date')} 第{week}周" if week else f"{data.get('date')} 非教学周"
    if tool == "web_fetch":
        return f"HTTP {data.get('status')} {data.get('bytes', 0)}B"
    return "ok"


class AgentLoop:
    """一次 chat = 一次规划 + 最多 N 步工具调用 + 一段答案。"""

    def __init__(
        self,
        registry: ToolRegistry,
        memory: SessionMemory | None = None,
        default_max_steps: int = 2,
        max_message_chars: int = 2000,
    ) -> None:
        self.registry = registry
        self.memory = memory or SessionMemory()
        self.default_max_steps = max(1, min(int(default_max_steps), 3))
        self.max_message_chars = max_message_chars

    def chat(
        self,
        message: str,
        session_id: str | None = None,
        max_steps: int | None = None,
        allow_llm: bool = True,
    ) -> dict:
        text = (message or "").strip()
        if not text:
            raise ToolError("EMPTY_MESSAGE", "消息不能为空")
        if len(text) > self.max_message_chars:
            raise ToolError("MESSAGE_TOO_LONG", f"消息长度 {len(text)} 字，超过上限 {self.max_message_chars} 字")
        sid = (session_id or "").strip() or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        planned = plan(text, self.registry, self.memory.recent_text(sid), allow_llm=allow_llm)
        limit = self.default_max_steps if max_steps is None else max(1, min(int(max_steps), 3))
        steps = planned["steps"][:limit]

        trace: list[dict] = []
        answers: list[str] = []
        citations: list[dict] = []
        for step in steps:
            name = step["tool"]
            args = step.get("args") or {}
            tool_started = time.perf_counter()
            try:
                data = self.registry.call(name, args)
            except ToolError as exc:
                trace.append(
                    {
                        "tool": name,
                        "args": args,
                        "ok": False,
                        "latency_ms": round((time.perf_counter() - tool_started) * 1000, 1),
                        "error": exc.code,
                        "message": exc.message,
                        "summary": None,
                    }
                )
                answers.append(f"（{name} 执行失败 {exc.code}：{exc.message}）")
                continue
            trace.append(
                {
                    "tool": name,
                    "args": args,
                    "ok": True,
                    "latency_ms": round((time.perf_counter() - tool_started) * 1000, 1),
                    "error": None,
                    "message": None,
                    "summary": _digest(name, data),
                }
            )
            if name == "policy_search":
                answers.append(data.get("answer", ""))
                for item in data.get("contexts", []):
                    citations.append(
                        {
                            "id": item["id"],
                            "doc_id": item["doc_id"],
                            "title": item["title"],
                            "snippet": item["snippet"],
                        }
                    )
            elif name == "calendar":
                answers.append(_calendar_sentence(data))
            elif name == "web_fetch":
                answers.append(_web_sentence(data))

        answer = "\n".join(part for part in answers if part).strip() or "没有可用的工具结果。"
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        self.memory.add(sid, "user", text)
        self.memory.add(
            sid,
            "assistant",
            answer,
            {"tools": [item["tool"] for item in trace], "planner": planned["planner"]},
        )
        return {
            "session_id": sid,
            "message": text,
            "answer": answer,
            "tool_calls": trace,
            "citations": citations,
            "used_tools": [item["tool"] for item in trace],
            "planner": planned["planner"],
            "reason": planned.get("reason", ""),
            "steps_used": len(trace),
            "latency_ms": latency_ms,
        }
