"""向量化：默认零依赖哈希向量，可选接 OpenAI 兼容的 embedding API。"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from typing import Sequence

import numpy as np

from .text import normalize


class Embedder:
    name = "base"
    dim = 0

    def embed(self, texts: Sequence[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class HashingEmbedder(Embedder):
    """字符 2/3-gram 哈希到固定维度并做符号散列，再 L2 归一化。

    零依赖、确定性、中文友好，适合做基线；接上真实模型后可无缝替换。
    """

    name = "hash"

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def _one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        chars = [c for c in normalize(text).lower() if not c.isspace()]
        grams = []
        for n in (2, 3):
            for i in range(len(chars) - n + 1):
                grams.append("".join(chars[i:i + n]))
        if not grams:
            grams = [normalize(text).lower() or "_empty_"]
        for g in grams:
            h = int.from_bytes(hashlib.md5(g.encode("utf-8")).digest()[:8], "big")
            vec[h % self.dim] += 1.0 if (h >> 63) & 1 == 0 else -1.0
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm else vec

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._one(t) for t in texts])


class ApiEmbedder(Embedder):
    """OpenAI 兼容的 /embeddings 接口（DeepSeek 兼容网关、硅基流动、通义等均可）。"""

    name = "api"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = 0

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), 32):
            batch = list(texts[i:i + 32])
            body = json.dumps({"model": self.model, "input": batch}).encode("utf-8")
            req = urllib.request.Request(
                self.base_url + "/embeddings",
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            out.extend(item["embedding"] for item in payload["data"])
        arr = np.asarray(out, dtype=np.float32)
        if arr.size:
            arr /= np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
        self.dim = int(arr.shape[1]) if arr.ndim == 2 else 0
        return arr


def load_embedder() -> Embedder:
    kind = os.environ.get("RAG_EMBEDDER", "hash").strip().lower()
    if kind == "api":
        base = os.environ.get("EMBED_BASE_URL", "")
        key = os.environ.get("EMBED_API_KEY", "")
        model = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
        if not base or not key:
            raise RuntimeError("RAG_EMBEDDER=api 时需要 EMBED_BASE_URL 和 EMBED_API_KEY")
        return ApiEmbedder(base, key, model)
    return HashingEmbedder()
