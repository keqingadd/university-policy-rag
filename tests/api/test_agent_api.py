"""Agent 接口用例（需要真实索引，跟随 tests/api 在 CI 的 api job 里跑）。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


def test_agent_tools_catalog(client) -> None:
    resp = client.get("/agent/tools")
    assert resp.status_code == 200
    tools = {item["name"]: item for item in resp.json()}
    assert set(tools) == {"policy_search", "calendar", "web_fetch"}
    for spec in tools.values():
        assert spec["description"]
        assert spec["parameters"]["type"] == "object"


def test_agent_chat_policy_question_uses_search(client) -> None:
    resp = client.post("/agent/chat", json={"message": "国家励志奖学金一年多少钱？"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["used_tools"] == ["policy_search"]
    assert body["tool_calls"][0]["ok"] is True
    assert body["citations"], "政策检索必须带出处"
    assert body["citations"][0]["doc_id"].endswith(".md")
    assert len(body["session_id"]) == 12
    assert body["planner"] == "rules"


def test_agent_chat_keeps_session_for_followup(client) -> None:
    first = client.post("/agent/chat", json={"message": "国家励志奖学金的申请条件是什么？"}).json()
    second = client.post(
        "/agent/chat",
        json={"message": "那金额是多少", "session_id": first["session_id"]},
    )
    assert second.status_code == 200, second.text
    assert second.json()["session_id"] == first["session_id"]
    assert second.json()["used_tools"] == ["policy_search"]


def test_agent_chat_calendar_tool(client) -> None:
    resp = client.post("/agent/chat", json={"message": "今天第几教学周了"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["used_tools"] == ["calendar"]
    assert "教学周" in body["answer"]


def test_agent_chat_blocks_private_url(client) -> None:
    resp = client.post("/agent/chat", json={"message": "看看这个 http://127.0.0.1:8000/health"})
    assert resp.status_code == 200, resp.text
    call = resp.json()["tool_calls"][0]
    assert call["tool"] == "web_fetch"
    assert call["ok"] is False
    assert call["error"] == "FORBIDDEN_URL"


@pytest.mark.parametrize(
    "payload, code",
    [
        ({"message": ""}, "EMPTY_MESSAGE"),
        ({"message": "   "}, "EMPTY_MESSAGE"),
        ({"message": "长" * 2001}, "MESSAGE_TOO_LONG"),
    ],
)
def test_agent_chat_business_errors(client, payload, code) -> None:
    resp = client.post("/agent/chat", json=payload)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"]["code"] == code
    assert body["error"]["request_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "奖学金", "max_steps": 9},
        {"message": "奖学金", "session_id": "带空格 的"},
        {"message": "奖学金", "unexpected": 1},
        {},
    ],
)
def test_agent_chat_invalid_params(client, payload) -> None:
    resp = client.post("/agent/chat", json=payload)
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAM"
    assert body["error"]["details"]["fields"]
