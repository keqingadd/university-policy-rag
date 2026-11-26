"""locust 压测脚本：对 POST /query 做并发压测。

用法（需先启动服务）：
    locust -f loadtest/locustfile.py --host http://127.0.0.1:8000

无头模式（CI / 本机跑数）：
    locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 \
        --headless -u 20 -r 5 -t 60s --csv reports/locust
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task

QUESTIONS = [
    "国家励志奖学金的申请条件是什么？",
    "家庭经济困难学生认定需要哪些材料？",
    "助学贷款的还款方式有哪些？",
    "转专业的申请时间是什么时候？",
    "勤工助学岗位怎么申请？",
    "学分绩点是怎么计算的？",
]

BAD_CASES = [
    {"question": ""},
    {"question": "   "},
    {"question": "啊" * 2500},
]


class QueryUser(HttpUser):
    """模拟调用 /query 的前端用户：多数正常提问，少量异常输入。"""

    wait_time = between(0.5, 2.0)

    @task(18)
    def query_normal(self) -> None:
        payload = {
            "question": random.choice(QUESTIONS),
            "top_k": random.choice([3, 5]),
            "mode": random.choice(["hybrid", "bm25", "vector"]),
        }
        with self.client.post("/query", json=payload, name="/query [normal]", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"期望 200，实际 {resp.status_code}")
                return
            body = resp.json()
            if not body.get("contexts"):
                resp.failure("正常问题未召回任何 context")
                return
            # 服务端自报延迟，用于交叉核对网关侧统计
            latency = body.get("latency_ms")
            if latency is None or latency > 3000:
                resp.failure(f"latency_ms 异常: {latency}")

    @task(4)
    def query_no_hit(self) -> None:
        payload = {"question": "量子纠缠通信卫星的轨道参数如何验证？"}
        with self.client.post("/query", json=payload, name="/query [no-hit]", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"无命中问题应降级返回 200，实际 {resp.status_code}")

    @task(3)
    def query_bad_input(self) -> None:
        with self.client.post("/query", json=random.choice(BAD_CASES), name="/query [bad-input]", catch_response=True) as resp:
            if resp.status_code not in (400, 422):
                resp.failure(f"非法输入期望 400/422，实际 {resp.status_code}")
                return
            if "error" not in resp.json():
                resp.failure("错误响应缺少 error 字段")

    @task(2)
    def health(self) -> None:
        with self.client.get("/health", name="/health", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"health 期望 200，实际 {resp.status_code}")
                return
            if resp.json().get("status") != "ok":
                resp.failure("health status 不是 ok")
