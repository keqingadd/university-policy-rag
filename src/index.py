"""索引：BM25 关键词检索 + 向量检索 + RRF 混合排序。"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .embedder import Embedder, load_embedder
from .query import expand
from .text import Chunk, chunk_text, load_documents, tokenize


class BM25:
    def __init__(self, token_lists: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.token_lists = [list(t) for t in token_lists]
        self.k1, self.b = k1, b
        self.n = len(self.token_lists)
        self.tf = [Counter(t) for t in self.token_lists]
        self.dl = np.asarray([len(t) for t in self.token_lists], dtype=float)
        self.avgdl = float(self.dl.mean()) if self.n else 0.0
        df: Counter = Counter()
        for t in self.token_lists:
            df.update(set(t))
        self.idf = {w: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def scores(self, query_tokens: Sequence[str]) -> np.ndarray:
        scores = np.zeros(self.n, dtype=float)
        for w in dict.fromkeys(query_tokens):
            idf = self.idf.get(w)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(w, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * self.dl[i] / (self.avgdl or 1.0))
                scores[i] += idf * f * (self.k1 + 1) / denom
        return scores


def _rrf(rankings: Iterable[Sequence[int]], k: int = 60) -> list[tuple[int, float]]:
    fused: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] += 1.0 / (k + rank + 1)
    return sorted(fused.items(), key=lambda kv: -kv[1])


class RagIndex:
    def __init__(
        self,
        chunks: list[Chunk],
        tokens: list[list[str]],
        embeddings: np.ndarray,
        embedder_name: str = "hash",
        dim: int = 0,
    ) -> None:
        self.chunks = chunks
        self.tokens = tokens
        self.embeddings = embeddings
        self.embedder_name = embedder_name
        self.dim = dim or (int(embeddings.shape[1]) if embeddings.ndim == 2 and embeddings.size else 0)
        self.bm25 = BM25(tokens)

    # ---------- build / persist ----------
    @classmethod
    def build(cls, docs_dir: str, embedder: Embedder | None = None, size: int = 500, overlap: int = 80) -> "RagIndex":
        embedder = embedder or load_embedder()
        docs = load_documents(docs_dir)
        chunks: list[Chunk] = []
        for doc_id, title, raw in docs:
            for i, text in enumerate(chunk_text(raw, size=size, overlap=overlap)):
                chunks.append(Chunk(doc_id=doc_id, title=title, index=i, text=text))
        tokens = [tokenize(c.text) for c in chunks]
        embeddings = embedder.embed([c.text for c in chunks]) if chunks else np.zeros((0, 0), dtype=np.float32)
        return cls(chunks, tokens, embeddings, embedder_name=embedder.name, dim=embedder.dim)

    def save(self, out_dir: str | Path) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        meta = {
            "embedder": self.embedder_name,
            "dim": self.dim,
            "chunks": [c.__dict__ for c in self.chunks],
            "tokens": self.tokens,
        }
        (out / "index.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        np.save(out / "embeddings.npy", self.embeddings)
        return out

    @classmethod
    def load(cls, index_dir: str | Path, embedder: Embedder | None = None) -> "RagIndex":
        d = Path(index_dir)
        meta = json.loads((d / "index.json").read_text(encoding="utf-8"))
        embeddings = np.load(d / "embeddings.npy")
        embedder = embedder or load_embedder()
        if embedder.name != meta["embedder"]:
            raise RuntimeError(
                f"索引是用 {meta['embedder']} 建的，当前 embedder 是 {embedder.name}，请重新 build-index。"
            )
        chunks = [Chunk(**c) for c in meta["chunks"]]
        return cls(chunks, meta["tokens"], embeddings, embedder_name=meta["embedder"], dim=meta.get("dim", 0))

    # ---------- search ----------
    def _vector_scores(self, query: str, embedder: Embedder) -> np.ndarray:
        if not len(self.chunks):
            return np.zeros(0)
        q = embedder.embed([query])[0]
        return self.embeddings @ q

    def search(
        self,
        query: str,
        top_k: int = 5,
        mode: str = "hybrid",
        embedder: Embedder | None = None,
        candidates: int = 30,
    ) -> list[dict]:
        """返回 [{chunk, score, bm25, vector, rank}]；mode ∈ hybrid | bm25 | vector。"""
        if not self.chunks:
            return []
        n = len(self.chunks)
        cand = min(max(top_k, candidates), n)
        expanded = expand(query)
        bm = self.bm25.scores(tokenize(expanded))
        bm_order = list(np.argsort(-bm)[:cand]) if mode in ("hybrid", "bm25") else []
        vec: np.ndarray | None = None
        vec_order: list[int] = []
        if mode in ("hybrid", "vector"):
            vec = self._vector_scores(expanded, embedder or load_embedder())
            vec_order = list(np.argsort(-vec)[:cand])
        if mode == "bm25":
            order = [(i, float(bm[i])) for i in bm_order]
        elif mode == "vector":
            order = [(i, float(vec[i]) if vec is not None else 0.0) for i in vec_order]
        else:
            order = _rrf([bm_order, vec_order])
        results = []
        for rank, (idx, score) in enumerate(order[:top_k]):
            results.append(
                {
                    "chunk": self.chunks[idx],
                    "score": score,
                    "bm25": float(bm[idx]),
                    "vector": float(vec[idx]) if vec is not None else 0.0,
                    "rank": rank + 1,
                }
            )
        return results
