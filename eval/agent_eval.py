"""Agent 评测：规划层「工具选择准确率」+ 可选真实执行统计。

用法：
  python eval/agent_eval.py                       # 只测规划层，离线可跑
  python eval/agent_eval.py --live --out reports/agent_eval.json
  python eval/agent_eval.py --live --base-url http://127.0.0.1:8000   # 打真实服务

--live 会真的调用工具：政策题走 data/index 的索引，网页题会发真实 HTTP 请求，
抓不到就如实记为执行失败（不影响工具选择准确率）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.loop import AgentLoop  # noqa: E402
from tools.calendar import calendar_tool  # noqa: E402
from tools.policy_search import policy_search_tool  # noqa: E402
from tools.registry import ToolRegistry  # noqa: E402
from tools.web_fetch import web_fetch_tool  # noqa: E402


def load_cases(path: Path) -> list[dict]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            cases.append(json.loads(line))
    return cases


def build_registry(index_dir: Path) -> ToolRegistry:
    service = None
    if (index_dir / "index.json").is_file():
        from api.config import load_settings
        from api.service import RagService

        service = RagService.from_dir(index_dir, load_settings())
    registry = ToolRegistry()
    registry.register(policy_search_tool(lambda: service))
    registry.register(calendar_tool(ROOT / "data" / "calendar" / "semester.json"))
    registry.register(web_fetch_tool())
    return registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="data/agent_eval/questions.jsonl")
    parser.add_argument("--index", default="data/index")
    parser.add_argument("--live", action="store_true", help="真的调用工具（政策题需要索引）")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    registry = build_registry(Path(args.index))
    loop = AgentLoop(registry)

    hits = 0
    per_category: dict[str, list[int]] = {}
    rows = []
    for case in cases:
        result = loop.chat(case["question"], session_id="eval-" + case["id"], allow_llm=False)
        chosen = result["used_tools"][0] if result["used_tools"] else "-"
        ok = chosen == case["expected_tool"]
        hits += int(ok)
        per_category.setdefault(case["category"], []).append(int(ok))
        row = {
            "id": case["id"],
            "question": case["question"],
            "expected": case["expected_tool"],
            "chosen": chosen,
            "correct": ok,
            "reason": result["reason"],
        }
        if args.live:
            call = result["tool_calls"][0]
            row.update(
                {
                    "tool_ok": call["ok"],
                    "tool_error": call["error"],
                    "answer_chars": len(result["answer"]),
                    "citations": len(result["citations"]),
                    "latency_ms": result["latency_ms"],
                }
            )
        rows.append(row)

    total = len(cases)
    print(f"| 类别 | 用例 | 选择正确 | 准确率 |")
    print("| --- | --- | --- | --- |")
    for category, values in per_category.items():
        print(f"| {category} | {len(values)} | {sum(values)} | {sum(values)/len(values):.2%} |")
    print(f"| 合计 | {total} | {hits} | {hits/total:.2%} |")

    summary = {"total": total, "correct": hits, "tool_selection_accuracy": round(hits / total, 4)}
    if args.live:
        executed = [row for row in rows if "tool_ok" in row]
        success = sum(1 for row in executed if row["tool_ok"])
        policy = [row for row in executed if row["expected"] == "policy_search"]
        with_citation = sum(1 for row in policy if row["citations"] > 0)
        latencies = sorted(row["latency_ms"] for row in executed)
        summary.update(
            {
                "executed": len(executed),
                "tool_success": success,
                "tool_success_rate": round(success / len(executed), 4) if executed else None,
                "policy_citation_rate": round(with_citation / len(policy), 4) if policy else None,
                "latency_ms_p50": latencies[len(latencies) // 2] if latencies else None,
                "latency_ms_p95": latencies[int(len(latencies) * 0.95) - 1] if latencies else None,
                "errors": dict(Counter(row["tool_error"] for row in executed if row["tool_error"])),
            }
        )
    print(json.dumps(summary, ensure_ascii=False))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("report -> " + str(out))
    return 0 if hits == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
