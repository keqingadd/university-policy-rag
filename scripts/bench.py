"""最小压测脚本：不依赖 locust，直接打 /query 算出 QPS 与延迟分位数。

用法：
    python scripts/bench.py --url http://127.0.0.1:8000 --requests 200 --concurrency 8
    python scripts/bench.py --requests 500 --concurrency 20 --json reports/bench.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import httpx

QUESTIONS = [
    "国家励志奖学金的申请条件是什么？",
    "家庭经济困难学生认定需要哪些材料？",
    "助学贷款的还款方式有哪些？",
    "转专业的申请时间是什么时候？",
    "勤工助学岗位怎么申请？",
    "学分绩点是怎么计算的？",
]


def percentile(values: list[float], q: float) -> float:
    """最近秩法分位数，q∈[0,1]。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * len(ordered) + 0.5)) - 1))
    return ordered[idx]


@dataclass
class Result:
    latencies: list[float] = field(default_factory=list)
    server_latencies: list[float] = field(default_factory=list)
    statuses: dict[int, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def add(self, status: int, elapsed_ms: float, server_ms: float | None) -> None:
        self.latencies.append(elapsed_ms)
        if server_ms is not None:
            self.server_latencies.append(server_ms)
        self.statuses[status] = self.statuses.get(status, 0) + 1


def run(url: str, total: int, concurrency: int, timeout: float) -> tuple[Result, float]:
    result = Result()
    base = url.rstrip("/")

    # trust_env=False：Windows 上开着系统代理时，httpx 会读注册表代理设置，
    # 把发往 127.0.0.1 的本地压测流量也塞进代理，结果全是 502。压测必须直连。
    client = httpx.Client(trust_env=False, timeout=timeout)

    def one(i: int) -> None:
        payload = {"question": QUESTIONS[i % len(QUESTIONS)], "top_k": 5}
        started = time.perf_counter()
        try:
            resp = client.post(f"{base}/query", json=payload)
            elapsed_ms = (time.perf_counter() - started) * 1000
            server_ms = None
            if resp.status_code == 200:
                server_ms = resp.json().get("latency_ms")
            result.add(resp.status_code, elapsed_ms, server_ms)
        except Exception as exc:  # noqa: BLE001
            result.add(0, (time.perf_counter() - started) * 1000, None)
            result.errors.append(f"{type(exc).__name__}: {exc}")

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(one, range(total)))
    wall = time.perf_counter() - started
    return result, wall


def summarize(result: Result, wall: float, total: int) -> dict:
    ok = result.statuses.get(200, 0)
    lat = result.latencies
    return {
        "requests": total,
        "concurrency_note": "见命令行 --concurrency",
        "success": ok,
        "failed": total - ok,
        "statuses": {str(k): v for k, v in sorted(result.statuses.items())},
        "wall_seconds": round(wall, 3),
        "qps": round(total / wall, 2) if wall > 0 else 0.0,
        "latency_ms": {
            "mean": round(statistics.fmean(lat), 2) if lat else 0.0,
            "p50": round(percentile(lat, 0.50), 2),
            "p90": round(percentile(lat, 0.90), 2),
            "p95": round(percentile(lat, 0.95), 2),
            "p99": round(percentile(lat, 0.99), 2),
            "max": round(max(lat), 2) if lat else 0.0,
        },
        "server_latency_ms": {
            "p50": round(percentile(result.server_latencies, 0.50), 2),
            "p95": round(percentile(result.server_latencies, 0.95), 2),
        },
        "error_rate": round((total - ok) / total * 100, 2) if total else 0.0,
        "errors": result.errors[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="对 /query 施加固定并发压测")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    result, wall = run(args.url, args.requests, args.concurrency, args.timeout)
    summary = summarize(result, wall, args.requests)
    summary["concurrency"] = args.concurrency
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
