"""并发用例：5 个线程同时打接口，验证索引只读、无共享可变状态。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

QUESTIONS = [
    "家庭经济困难学生认定多久评一次？",
    "国家奖学金一年多少钱？",
    "助学贷款额度是多少？",
    "休学最长时间是多久？",
    "勤工助学每周能工作几小时？",
]


@pytest.mark.api
def test_concurrent_queries(client):
    def call(question: str):
        return client.post("/query", json={"question": question, "top_k": 5})

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(call, QUESTIONS * 3))

    assert len(responses) == 15
    for response in responses:
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["answer"]
        assert body["contexts"]

    request_ids = {r.headers.get("X-Request-ID") for r in responses}
    assert len(request_ids) == len(responses), "并发请求的 request_id 出现重复"


@pytest.mark.api
def test_concurrent_mixed_errors(client):
    """并发里混入非法请求，错误不应污染正常请求。"""
    def call(index: int):
        if index % 3 == 0:
            return client.post("/query", json={"question": ""})
        if index % 3 == 1:
            return client.post("/query", json={"question": "国家奖学金多少钱？", "top_k": 99})
        return client.post("/query", json={"question": "国家奖学金多少钱？"})

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(call, range(15)))

    for index, response in enumerate(responses):
        expected = 400 if index % 3 == 0 else 422 if index % 3 == 1 else 200
        assert response.status_code == expected, (index, response.status_code, response.text)
