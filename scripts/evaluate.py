"""检索评测：python scripts/evaluate.py --mode hybrid"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evaluate import evaluate, load_questions, render_markdown  # noqa: E402
from src.index import RagIndex  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 检索评测")
    parser.add_argument("--index", default="data/index")
    parser.add_argument("--questions", default="data/eval/questions.jsonl")
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "bm25", "vector"])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--report", default="reports/eval_report.md")
    args = parser.parse_args()

    index = RagIndex.load(args.index)
    questions = load_questions(args.questions)
    report = evaluate(index, questions, top_k=args.top_k, mode=args.mode)

    print(f"mode={report['mode']}  n={report['n']}")
    print(f"Hit@1={report['hit@1']:.2%}  Hit@3={report['hit@3']:.2%}  Hit@5={report['hit@5']:.2%}  MRR={report['mrr']:.4f}")
    print(f"平均检索耗时 {report['avg_latency_ms']} ms")
    for row in report["rows"]:
        mark = "✅" if row["rank"] else "❌"
        print(f"  {mark} rank={row['rank'] or '-'}  {row['question']}")

    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(report), encoding="utf-8")
    print(f"\n报告已写入 {out}")


if __name__ == "__main__":
    main()
