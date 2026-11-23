"""最小单元测试：python -m unittest discover -s tests -v"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.embedder import HashingEmbedder  # noqa: E402
from src.index import RagIndex  # noqa: E402
from src.query import expand  # noqa: E402
from src.text import chunk_text, tokenize  # noqa: E402


class TextTest(unittest.TestCase):
    def test_tokenize_cjk(self) -> None:
        tokens = tokenize("家庭经济困难学生")
        self.assertIn("家庭", tokens)
        self.assertIn("家庭经", tokens)

    def test_tokenize_latin(self) -> None:
        self.assertIn("lpr", tokenize("LPR 减 60 个基点"))

    def test_chunk_keeps_heading(self) -> None:
        text = "# 标题\n\n## 小节A\n这是内容A。\n\n## 小节B\n这是内容B。"
        chunks = chunk_text(text, size=100)
        self.assertTrue(any("小节A" in c for c in chunks))
        self.assertTrue(all(len(c) <= 160 for c in chunks))

    def test_chunk_overlap(self) -> None:
        body = "第一句。" * 200
        chunks = chunk_text(body, size=120, overlap=30)
        self.assertGreater(len(chunks), 1)


class QueryTest(unittest.TestCase):
    def test_expand_colloquial(self) -> None:
        expanded = expand("国奖能拿多少钱")
        self.assertIn("国家奖学金", expanded)
        self.assertIn("国奖能拿多少钱", expanded)  # 原查询保留

    def test_expand_no_hit_returns_original(self) -> None:
        self.assertEqual(expand("今天天气怎么样"), "今天天气怎么样")


class IndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = RagIndex.build("data/docs", embedder=HashingEmbedder())

    def test_index_not_empty(self) -> None:
        self.assertGreater(len(self.index.chunks), 0)
        self.assertEqual(self.index.embeddings.shape[1], 1024)

    def test_search_finds_expected_doc(self) -> None:
        hits = self.index.search("勤工助学每周不超过多少小时", top_k=3)
        docs = [h["chunk"].doc_id for h in hits]
        self.assertIn("05-高等学校勤工助学管理办法.md", docs)

    def test_unknown_question_still_returns(self) -> None:
        hits = self.index.search("今天天气怎么样", top_k=5)
        self.assertEqual(len(hits), 5)


if __name__ == "__main__":
    unittest.main()
