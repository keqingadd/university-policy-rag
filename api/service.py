"""服务层：索引只加载一次，负责参数校验和调用 RAG 主流程。

RagPipeline 本身是无状态的（索引只读），因此按 (top_k, mode) 缓存实例即可，
并发请求共用同一份索引，不会重复读盘。
"""
from __future__ import annotations

import threading
from pathlib import Path

from src.index import RagIndex
from src.pipeline import RagPipeline

from .config import Settings
from .errors import AppError


class RagService:
    def __init__(self, index: RagIndex, settings: Settings) -> None:
        self.settings = settings
        self.index = index
        self._pipelines: dict[tuple[int, str], RagPipeline] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_dir(cls, index_dir: str | Path, settings: Settings) -> "RagService":
        path = Path(index_dir)
        if not (path / "index.json").is_file():
            raise AppError("INDEX_NOT_READY", f"索引不存在：{path}，请先运行 python scripts/build_index.py")
        try:
            index = RagIndex.load(path)
        except Exception as exc:  # 索引损坏 / embedder 不匹配都归到这里
            raise AppError("INDEX_NOT_READY", f"索引加载失败：{exc}") from exc
        return cls(index, settings)

    def _pipeline(self, top_k: int, mode: str) -> RagPipeline:
        key = (top_k, mode)
        with self._lock:
            pipeline = self._pipelines.get(key)
            if pipeline is None:
                pipeline = RagPipeline(self.index, top_k=top_k, mode=mode)
                self._pipelines[key] = pipeline
            return pipeline

    def normalize_question(self, question: str) -> str:
        text = (question or "").strip()
        if not text:
            raise AppError("EMPTY_QUESTION")
        if len(text) > self.settings.max_question_chars:
            raise AppError(
                "QUESTION_TOO_LONG",
                f"问题长度 {len(text)} 字，超过上限 {self.settings.max_question_chars} 字",
            )
        return text

    def ask(self, question: str, top_k: int | None = None, mode: str | None = None) -> dict:
        text = self.normalize_question(question)
        pipeline = self._pipeline(
            top_k or self.settings.default_top_k,
            mode or self.settings.default_mode,
        )
        return pipeline.ask(text)

    def health(self) -> dict:
        return {
            "status": "ok",
            "chunks": len(self.index.chunks),
            "embedder": self.index.embedder_name,
            "version": self.settings.version,
            "index_dir": str(self.settings.index_dir),
        }
