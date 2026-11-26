"""YAML 数据驱动的接口测试。

每条用例 = 一次 HTTP 调用 + 一组断言。新增/修改用例只改 cases.yaml。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = Path(__file__).with_name("cases.yaml")
PAYLOADS = {
    "__LONG_2001__": "啊" * 2001,
    "__LONG_5000__": "啊" * 5000,
    "__LEN_2000__": "国家奖学金" * 400,  # 正好 2000 字，卡在上限
}


def _load_cases() -> list[dict]:
    raw = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    cases = raw["cases"]
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), "cases.yaml 里 id 重复了"
    for case in cases:
        body = case.get("json") or {}
        for key, value in list(body.items()):
            if isinstance(value, str) and value in PAYLOADS:
                body[key] = PAYLOADS[value]
    return cases


CASES = _load_cases()


def _assert_case(case: dict, response, body) -> None:
    expect = case["expect"]
    label = f"[{case['id']}] {case.get('title', '')}"

    assert response.status_code == expect["status"], (
        f"{label} 状态码不符：期望 {expect['status']}，实际 {response.status_code}，body={response.text}"
    )

    for header in expect.get("headers", []):
        assert header in response.headers, f"{label} 缺少响应头 {header}"

    for header, value in (expect.get("header_equals") or {}).items():
        assert response.headers.get(header) == value, f"{label} 响应头 {header} 不等于 {value}"

    for key in expect.get("json_keys", []):
        assert key in body, f"{label} 响应缺少字段 {key}，实际字段={sorted(body)}"

    if "error_code" in expect:
        assert "error" in body, f"{label} 期望错误结构，实际 body={body}"
        error = body["error"]
        assert error["code"] == expect["error_code"], (
            f"{label} 错误码不符：期望 {expect['error_code']}，实际 {error.get('code')}"
        )
        assert error.get("message"), f"{label} 错误信息为空"
        assert error.get("request_id"), f"{label} 错误响应缺少 request_id"

    for key, value in (expect.get("equals") or {}).items():
        assert body.get(key) == value, f"{label} 字段 {key} 期望 {value!r}，实际 {body.get(key)!r}"

    for key, value in (expect.get("contains") or {}).items():
        actual = body.get(key)
        assert isinstance(actual, str) and value in actual, (
            f"{label} 字段 {key} 应包含 {value!r}，实际为 {actual!r}"
        )

    if "min_contexts" in expect:
        contexts = body.get("contexts") or []
        assert len(contexts) >= expect["min_contexts"], f"{label} contexts 数量不足：{len(contexts)}"

    if "max_contexts" in expect:
        contexts = body.get("contexts") or []
        assert len(contexts) <= expect["max_contexts"], f"{label} contexts 超量：{len(contexts)}"

    if "max_latency_ms" in expect:
        latency = body.get("latency_ms")
        assert isinstance(latency, (int, float)), f"{label} 缺少 latency_ms"
        assert latency <= expect["max_latency_ms"], (
            f"{label} 延迟过高：{latency}ms > {expect['max_latency_ms']}ms"
        )

    if "min_chunks" in expect:
        chunks = body.get("chunks")
        assert isinstance(chunks, int) and chunks >= expect["min_chunks"], (
            f"{label} chunks 不足：{chunks}"
        )


@pytest.mark.api
@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_api_cases(client, case):
    response = client.request(
        case.get("method", "POST"),
        case.get("path", "/query"),
        json=case.get("json"),
        headers=case.get("headers"),
    )
    _assert_case(case, response, response.json())


@pytest.mark.api
def test_openapi_contract(client):
    """契约自检：两个接口都在 OpenAPI 里，且 question 是必填字段。"""
    schema = client.get("/openapi.json").json()
    assert "/query" in schema["paths"]
    assert "/health" in schema["paths"]
    query_schema = schema["components"]["schemas"]["QueryRequest"]
    assert "question" in query_schema["required"]
