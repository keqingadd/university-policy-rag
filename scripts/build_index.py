"""构建索引：python scripts/build_index.py --docs data/docs --out data/index"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.embedder import load_embedder  # noqa: E402
from src.index import RagIndex  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 RAG 索引")
    parser.add_argument("--docs", default="data/docs", help="文档目录（.md/.txt）")
    parser.add_argument("--out", default="data/index", help="索引输出目录")
    parser.add_argument("--size", type=int, default=500, help="切片长度")
    parser.add_argument("--overlap", type=int, default=80, help="切片重叠")
    args = parser.parse_args()

    embedder = load_embedder()
    index = RagIndex.build(args.docs, embedder=embedder, size=args.size, overlap=args.overlap)
    saved = index.save(args.out)
    docs = {c.doc_id for c in index.chunks}
    print(f"✅ 索引已生成：{saved}")
    print(f"   文档 {len(docs)} 篇 / 切片 {len(index.chunks)} 个 / 向量维度 {index.dim} / embedder={index.embedder_name}")
    if not index.chunks:
        print("⚠️  没有读到任何文档，检查 --docs 路径和文件后缀（.md/.txt）")


if __name__ == "__main__":
    main()
