"""命令行问答：python scripts/ask.py "你们支持私有化部署吗？" """
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.index import RagIndex  # noqa: E402
from src.pipeline import RagPipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="知识库问答")
    parser.add_argument("question", nargs="*", help="问题")
    parser.add_argument("--index", default="data/index")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "bm25", "vector"])
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    if not question:
        question = "家庭经济困难学生认定多久评一次？"
        print(f"（未提供问题，使用示例：{question}）")

    pipe = RagPipeline(RagIndex.load(args.index), top_k=args.top_k, mode=args.mode)
    result = pipe.ask(question)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"\n问题：{result['question']}")
    print(f"\n回答（{'大模型' if result['used_llm'] else '抽取式'}，{result['latency_ms']} ms）：\n{result['answer']}\n")
    print("引用来源：")
    for ctx in result["contexts"]:
        print(f"  [{ctx['id']}] {ctx['doc_id']} · {ctx['title']} · 块{ctx['chunk_index']} · score={ctx['score']}")


if __name__ == "__main__":
    main()
