"""工具规划：默认用可解释的关键词规则，配置了 LLM_API_KEY 才尝试大模型规划。

为什么默认不是大模型：这台机器没有 API Key，规则版能保证测试与评测可复现；
大模型只作为可选增强，解析失败自动回落到规则。
"""
from __future__ import annotations

import json
import re

from src import llm
from tools.registry import ToolError, ToolRegistry

_URL_RE = re.compile(r"https?://[^\s\u4e00-\u9fff\"'<>]+")
_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")

DEFAULT_TOOL = "policy_search"


def extract_url(message: str) -> str | None:
    match = _URL_RE.search(message or "")
    if not match:
        return None
    return match.group(0).rstrip(".,;)]}")


def extract_date(message: str) -> str | None:
    match = _DATE_RE.search(message or "")
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _keyword_score(message: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for word in keywords if word and word in message)


def _rule_plan(message: str, registry: ToolRegistry) -> dict:
    url = extract_url(message)
    if url and registry.has("web_fetch"):
        return {
            "planner": "rules",
            "reason": "消息里带 URL，交给网页抓取工具",
            "steps": [{"tool": "web_fetch", "args": {"url": url}, "reason": "包含 http(s) 链接"}],
        }

    best: tuple[int, str] | None = None
    for name in registry.names():
        if name == "web_fetch":
            continue  # 没有 URL 时抓不了网页
        tool = registry.get(name)
        score = _keyword_score(message, tool.keywords)
        if score and (best is None or score > best[0]):
            best = (score, name)

    if best is not None:
        score, name = best
        args: dict = {}
        if name == "policy_search":
            args = {"question": message}
        elif name == "calendar":
            date = extract_date(message)
            if date:
                args = {"date": date}
        elif name == "web_fetch":
            args = {"url": url or ""}
        return {
            "planner": "rules",
            "reason": f"命中 {name} 的 {score} 个关键词",
            "steps": [{"tool": name, "args": args, "reason": "关键词命中"}],
        }

    fallback = DEFAULT_TOOL if registry.has(DEFAULT_TOOL) else registry.names()[0]
    args = {"question": message} if fallback == "policy_search" else {}
    return {
        "planner": "rules",
        "reason": "没有命中任何工具关键词，回落到知识库检索",
        "steps": [{"tool": fallback, "args": args, "reason": "默认工具"}],
    }


def _parse_json_object(raw: str) -> dict:
    """容忍模型返回 ```json 代码块的情况。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text)


def _llm_plan(message: str, registry: ToolRegistry, history_text: str) -> dict | None:
    """让模型输出 {"tool":..,"args":{..}}；任何异常都返回 None 交给规则回落。"""
    catalog = json.dumps(registry.specs(), ensure_ascii=False)
    prompt = (
        "你是工具路由器。可用工具：\n" + catalog + "\n\n"
        "只输出一个 JSON 对象，形如 {\"tool\": \"policy_search\", \"args\": {\"question\": \"...\"}}。"
        "不要解释、不要 markdown。\n"
        + (f"最近对话：\n{history_text}\n" if history_text else "")
        + f"用户消息：{message}"
    )
    try:
        raw = llm.chat([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=300)
        payload = _parse_json_object(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    name = payload.get("tool")
    args = payload.get("args") or {}
    if not isinstance(name, str) or not registry.has(name) or not isinstance(args, dict):
        return None
    if name == "policy_search" and "question" not in args:
        args["question"] = message
    return {
        "planner": "llm",
        "reason": "大模型选择",
        "steps": [{"tool": name, "args": args, "reason": "LLM"}],
    }


def plan(message: str, registry: ToolRegistry, history_text: str = "", allow_llm: bool = True) -> dict:
    text = (message or "").strip()
    if not text:
        raise ToolError("EMPTY_MESSAGE", "消息不能为空")
    if allow_llm and llm.is_configured():
        planned = _llm_plan(text, registry, history_text)
        if planned is not None:
            return planned
    return _rule_plan(text, registry)
