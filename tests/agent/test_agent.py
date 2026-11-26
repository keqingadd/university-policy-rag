"""Agent 工具层与规划器单测（不需要索引、不联网）。

设计取舍：接口测试需要真索引（tests/api 会被 CI 的 unit job 排除），而工具层
与规划器应当能在任何机器上跑，所以这里用假 service + 假 fetcher。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
import yaml

from agent.loop import AgentLoop
from agent.memory import SessionMemory
from agent.planner import extract_date, extract_url, plan
from tools.calendar import calendar_tool
from tools.policy_search import policy_search_tool
from tools.registry import ToolError, ToolRegistry
from tools.web_fetch import clean_html, web_fetch_tool

CASES = Path(__file__).with_name("cases.yaml")


class FakeService:
    """假 RAG 服务：只验证“工具被正确调用”，不验证检索质量。"""

    def __init__(self, answer: str = "（假答案）国家励志奖学金每生每年 5000 元。") -> None:
        self.answer = answer
        self.calls: list[tuple[str, int | None]] = []

    def ask(self, question: str, top_k: int | None = None) -> dict:
        self.calls.append((question, top_k))
        return {
            "question": question,
            "answer": self.answer,
            "contexts": [
                {
                    "id": 1,
                    "doc_id": "03-学生资助政策14项.md",
                    "title": "学生资助政策",
                    "chunk_index": 0,
                    "score": 0.87,
                    "snippet": "国家励志奖学金每生每年 5000 元。",
                }
            ],
            "latency_ms": 3.2,
            "used_llm": False,
            "mode": "hybrid",
            "top_k": top_k or 5,
        }


def fake_fetch(url: str, timeout: float, max_bytes: int) -> dict:
    return {
        "url": url,
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "bytes": 512,
        "body": "<html><head><title>关于寒假安排的通知</title><script>var x=1;</script></head>"
        "<body><p>2027 年寒假自 1 月 18 日开始，2 月 28 日结束。</p></body></html>",
    }


@pytest.fixture()
def calendar_file(tmp_path: Path) -> Path:
    path = tmp_path / "semester.json"
    path.write_text(
        json.dumps(
            {
                "term": {"name": "测试学期", "start": "2026-09-07", "end": "2027-01-17"},
                "events": [
                    {"name": "国庆节", "kind": "holiday", "start": "2026-10-01", "end": "2026-10-07"},
                    {"name": "期末考试周", "kind": "exam", "start": "2027-01-04", "end": "2027-01-15"},
                    {"name": "寒假", "kind": "break", "start": "2027-01-18", "end": "2027-02-28"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def registry(calendar_file: Path) -> ToolRegistry:
    service = FakeService()
    reg = ToolRegistry()
    reg.register(policy_search_tool(lambda: service))
    reg.register(calendar_tool(calendar_file, today=dt.date(2026, 11, 27)))
    reg.register(web_fetch_tool(fetcher=fake_fetch))
    return reg


def load_cases() -> list[dict]:
    data = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    return data["cases"]


@pytest.mark.parametrize("case", load_cases(), ids=[c["question"][:18] for c in load_cases()])
def test_tool_selection(registry: ToolRegistry, case: dict) -> None:
    result = AgentLoop(registry).chat(case["question"])
    assert result["used_tools"] == [case["tool"]], f"{case['question']} -> {result['used_tools']}"
    call = result["tool_calls"][0]
    for key, value in (case.get("expect_args") or {}).items():
        assert call["args"][key] == value
    assert result["answer"], "答案不能为空"
    if case.get("answer_contains"):
        assert case["answer_contains"] in result["answer"]


def test_planner_returns_reason_and_planner_name(registry: ToolRegistry) -> None:
    planned = plan("今天第几教学周", registry)
    assert planned["planner"] == "rules"
    assert planned["reason"]
    assert planned["steps"][0]["tool"] == "calendar"


def test_url_and_date_extraction() -> None:
    assert extract_url("看看 https://a.edu.cn/x?y=1 这个") == "https://a.edu.cn/x?y=1"
    assert extract_url("没有链接") is None
    assert extract_date("2026-1-5 是第几周") == "2026-01-05"
    assert extract_date("下周一") is None


def test_policy_search_forwards_top_k(registry: ToolRegistry) -> None:
    service = FakeService()
    reg = ToolRegistry()
    reg.register(policy_search_tool(lambda: service))
    data = reg.call("policy_search", {"question": "奖学金", "top_k": 3})
    assert data["n_contexts"] == 1
    assert service.calls == [("奖学金", 3)]


def test_policy_search_without_index_raises() -> None:
    reg = ToolRegistry()
    reg.register(policy_search_tool(lambda: None))
    with pytest.raises(ToolError) as err:
        reg.call("policy_search", {"question": "奖学金"})
    assert err.value.code == "INDEX_NOT_READY"


def test_registry_rejects_unknown_tool(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError) as err:
        registry.call("nope", {})
    assert err.value.code == "UNKNOWN_TOOL"
    assert "policy_search" in err.value.details["available"]


def test_registry_validates_required_and_unknown_args(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError) as err:
        registry.call("policy_search", {})
    assert err.value.code == "INVALID_TOOL_ARGS"
    assert err.value.details["fields"][0]["loc"] == "question"

    with pytest.raises(ToolError) as err2:
        registry.call("policy_search", {"question": "x", "unexpected": 1})
    assert err2.value.code == "INVALID_TOOL_ARGS"


def test_registry_validates_types_and_ranges(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError) as err:
        registry.call("policy_search", {"question": "x", "top_k": 99})
    assert err.value.code == "INVALID_TOOL_ARGS"
    with pytest.raises(ToolError) as err2:
        registry.call("policy_search", {"question": "x", "top_k": "3"})
    assert err2.value.code == "INVALID_TOOL_ARGS"
    with pytest.raises(ToolError) as err3:
        registry.call("policy_search", {"question": 123})
    assert err3.value.code == "INVALID_TOOL_ARGS"


def test_registry_rejects_duplicate_registration(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError) as err:
        registry.register(policy_search_tool(lambda: None))
    assert err.value.code == "DUPLICATE_TOOL"


def test_calendar_teaching_week_and_next_event(calendar_file: Path) -> None:
    tool = calendar_tool(calendar_file, today=dt.date(2026, 11, 27))
    data = tool.handler({"date": "2026-11-27"})
    assert data["in_term"] is True
    assert data["teaching_week"] == 12
    assert data["weekday"] == "周五"
    assert data["next_event"]["name"] == "期末考试周"
    assert data["next_event"]["days_until"] == 38


def test_calendar_holiday_and_break(calendar_file: Path) -> None:
    tool = calendar_tool(calendar_file, today=dt.date(2026, 10, 3))
    holiday = tool.handler({})
    assert holiday["current_event"]["name"] == "国庆节"

    winter = calendar_tool(calendar_file, today=dt.date(2027, 2, 1)).handler({})
    assert winter["in_term"] is False
    assert winter["in_break"] is True
    assert winter["current_event"]["name"] == "寒假"
    assert winter["teaching_week"] is None


def test_calendar_rejects_bad_date(calendar_file: Path) -> None:
    tool = calendar_tool(calendar_file)
    with pytest.raises(ToolError) as err:
        tool.handler({"date": "2026/11/27"})
    assert err.value.code == "INVALID_TOOL_ARGS"


def test_calendar_missing_file(tmp_path: Path) -> None:
    tool = calendar_tool(tmp_path / "missing.json")
    with pytest.raises(ToolError) as err:
        tool.handler({})
    assert err.value.code == "CALENDAR_NOT_READY"


def test_web_fetch_blocks_localhost_and_private_ip() -> None:
    tool = web_fetch_tool(fetcher=fake_fetch)
    for url in ("http://127.0.0.1:8000/health", "http://localhost/x", "http://192.168.1.2/x", "http://10.0.0.1/x"):
        with pytest.raises(ToolError) as err:
            tool.handler({"url": url})
        assert err.value.code == "FORBIDDEN_URL", url


def test_web_fetch_rejects_non_http_scheme() -> None:
    tool = web_fetch_tool(fetcher=fake_fetch)
    with pytest.raises(ToolError) as err:
        tool.handler({"url": "ftp://example.com/a.txt"})
    assert err.value.code == "FORBIDDEN_URL"


def test_web_fetch_cleans_html_and_keeps_title() -> None:
    data = web_fetch_tool(fetcher=fake_fetch).handler({"url": "https://www.example.edu.cn/notice/1.html"})
    assert data["title"] == "关于寒假安排的通知"
    assert "1 月 18 日" in data["text"]
    assert "var x" not in data["text"]


def test_clean_html_strips_script_style_and_truncates() -> None:
    title, text, truncated = clean_html("<html><title>T</title><style>a{}</style><p>正文</p></html>", 4)
    assert title == "T"
    assert text == "正文"
    assert truncated is False
    _, long_text, long_truncated = clean_html("<p>" + "字" * 100 + "</p>", 20)
    assert long_truncated is True
    assert len(long_text) == 20


def test_memory_keeps_turns_per_session() -> None:
    memory = SessionMemory(max_turns=4)
    memory.add("s1", "user", "第一轮")
    memory.add("s1", "assistant", "第一轮回答")
    memory.add("s2", "user", "另一个会话")
    assert len(memory.history("s1")) == 2
    assert len(memory.history("s2")) == 1
    for i in range(6):
        memory.add("s1", "user", f"补充 {i}")
    assert len(memory.history("s1")) == 4, "超过 max_turns 要丢最早的"
    assert memory.stats()["sessions"] == 2


def test_loop_generates_session_and_reuses_history(registry: ToolRegistry) -> None:
    loop = AgentLoop(registry)
    first = loop.chat("今天第几教学周")
    assert first["session_id"]
    second = loop.chat("那下周呢", session_id=first["session_id"])
    assert second["session_id"] == first["session_id"]
    assert len(loop.memory.history(first["session_id"])) == 4


def test_loop_rejects_empty_and_too_long_message(registry: ToolRegistry) -> None:
    loop = AgentLoop(registry, max_message_chars=50)
    with pytest.raises(ToolError) as err:
        loop.chat("   ")
    assert err.value.code == "EMPTY_MESSAGE"
    with pytest.raises(ToolError) as err2:
        loop.chat("长" * 51)
    assert err2.value.code == "MESSAGE_TOO_LONG"


def test_loop_reports_tool_failure_without_crashing() -> None:
    reg = ToolRegistry()
    reg.register(policy_search_tool(lambda: None))
    result = AgentLoop(reg).chat("奖学金多少钱")
    assert result["tool_calls"][0]["ok"] is False
    assert result["tool_calls"][0]["error"] == "INDEX_NOT_READY"
    assert "INDEX_NOT_READY" in result["answer"]
