"""最小单元测试：python -m unittest discover -s tests -v"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.embedder import HashingEmbedder  # noqa: E402
from src.index import RagIndex  # noqa: E402
from src.text import chunk_text, tokenize  # noqa: E402


class TextTest(unittest.TestCase):
    def test_tokenize_cjk(self) -> None:
        tokens = tokenize("私有化部署")
        self.assertIn("私有", tokens)
        self.assertIn("私有化", tokens)

    def test_tokenize_latin(self) -> None:
        self.assertIn("api", tokenize("API 限流 60 QPS"))

    def test_chunk_keeps_heading(self) -> None:
        text = "# 标题\n\n## 小节A\n这是内容A。\n\n## 小节B\n这是内容B。"
        chunks = chunk_text(text, size=100)
        self.assertTrue(any("小节A" in c for c in chunks))
        self.assertTrue(all(len(c) <= 160 for c in chunks))

    def test_chunk_overlap(self) -> None:
        body = "第一句。" * 200
        chunks = chunk_text(body, size=120, overlap=30)
        self.assertGreater(len(chunks), 1)


class IndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = RagIndex.build("data/docs", embedder=HashingEmbedder())

    def test_index_not_empty(self) -> None:
        self.assertGreater(len(self.index.chunks), 0)
        self.assertEqual(self.index.embeddings.shape[1], 1024)

    def test_search_finds_expected_doc(self) -> None:
        hits = self.index.search("私有化部署最低配置", top_k=3)
        docs = [h["chunk"].doc_id for h in hits]
        self.assertIn("02-部署与运维.md", docs)

    def test_unknown_question_still_returns(self) -> None:
        hits = self.index.search("今天天气怎么样", top_k=5)
        self.assertEqual(len(hits), 5)


if __name__ == "__main__":
    unittest.main()
