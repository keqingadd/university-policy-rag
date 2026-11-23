"""检索效果评测：Hit@k、MRR，可选生成质量人工/AI 评审。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .index import RagIndex


def load_questions(path: str | Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def evaluate(index: RagIndex, questions: list[dict], top_k: int = 5, mode: str = "hybrid") -> dict:
    rows = []
    hits_at = {1: 0, 3: 0, 5: 0}
    reciprocal_rank = 0.0
    latencies = []
    for item in questions:
        q = item["question"]
        gold = item.get("gold_doc", "")
        started = time.perf_counter()
        result = index.search(q, top_k=top_k, mode=mode)
        latencies.append((time.perf_counter() - started) * 1000)
        docs = [r["chunk"].doc_id for r in result]
        rank = docs.index(gold) + 1 if gold and gold in docs else None
        if rank:
            reciprocal_rank += 1.0 / rank
            for k in hits_at:
                if rank <= k:
                    hits_at[k] += 1
        rows.append({"question": q, "gold_doc": gold, "retrieved": docs, "rank": rank})
    n = max(len(questions), 1)
    return {
        "n": len(questions),
        "hit@1": round(hits_at[1] / n, 4),
        "hit@3": round(hits_at[3] / n, 4),
        "hit@5": round(hits_at[5] / n, 4),
        "mrr": round(reciprocal_rank / n, 4),
        "avg_latency_ms": round(sum(latencies) / n, 2),
        "mode": mode,
        "rows": rows,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# 检索评测报告",
        "",
        f"- 检索模式：{report['mode']}",
        f"- 题量：{report['n']}",
        f"- Hit@1：{report['hit@1']:.2%}",
        f"- Hit@3：{report['hit@3']:.2%}",
        f"- Hit@5：{report['hit@5']:.2%}",
        f"- MRR：{report['mrr']:.4f}",
        f"- 平均检索耗时：{report['avg_latency_ms']} ms",
        "",
        "| # | 问题 | 期望文档 | 名次 | 命中 |",
        "|---|---|---|---|---|",
    ]
    for i, row in enumerate(report["rows"], start=1):
        lines.append(
            f"| {i} | {row['question']} | {row['gold_doc']} | {row['rank'] or '-'} | {'✅' if row['rank'] else '❌'} |"
        )
    return "\n".join(lines) + "\n"
