"""RAG 主流程：检索 -> 拼上下文 -> 生成（无 API Key 时降级为抽取式回答）。"""
from __future__ import annotations

import time

from . import llm
from .embedder import load_embedder
from .index import RagIndex

SYSTEM_PROMPT = (
    "你是一名严谨的企业知识库助手。只能依据【参考资料】回答，不得编造。"
    "回答时用 [1][2] 这样的编号标注引用来源；如果资料不足以回答，直接说明"
    "“根据现有资料无法确定”，并指出还缺什么信息。用简体中文回答，控制在 300 字以内。"
)


def build_prompt(question: str, hits: list[dict]) -> str:
    lines = [f"【问题】{question}", "", "【参考资料】"]
    for i, hit in enumerate(hits, start=1):
        chunk = hit["chunk"]
        lines.append(f"[{i}] 来源：{chunk.doc_id}（{chunk.title}，块 {chunk.index}）")
        lines.append(hit["chunk"].text)
        lines.append("")
    lines.append("请依据以上资料作答，并标注引用编号。")
    return "\n".join(lines)


def extractive_answer(hits: list[dict], limit: int = 2) -> str:
    if not hits:
        return "没有检索到相关资料，建议换个问法，或把相关文档加入知识库。"
    parts = []
    for i, hit in enumerate(hits[:limit], start=1):
        text = hit["chunk"].text.strip().replace("\n", " ")
        if len(text) > 160:
            text = text[:160] + "…"
        parts.append(f"[{i}] {text}")
    return "（当前未配置大模型 API，以下为检索到的资料摘录）\n" + "\n".join(parts)


class RagPipeline:
    def __init__(self, index: RagIndex, top_k: int = 5, mode: str = "hybrid") -> None:
        self.index = index
        self.top_k = top_k
        self.mode = mode
        self.embedder = load_embedder()

    def ask(self, question: str) -> dict:
        started = time.perf_counter()
        hits = self.index.search(question, top_k=self.top_k, mode=self.mode, embedder=self.embedder)
        contexts = [
            {
                "id": i + 1,
                "doc_id": h["chunk"].doc_id,
                "title": h["chunk"].title,
                "chunk_index": h["chunk"].index,
                "score": round(h["score"], 4),
                "snippet": h["chunk"].text.strip().replace("\n", " ")[:180],
            }
            for i, h in enumerate(hits)
        ]
        used_llm = llm.is_configured()
        if used_llm:
            try:
                answer = llm.chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_prompt(question, hits)},
                    ]
                )
            except Exception as exc:  # 接口失败时不让整个 demo 崩
                answer = extractive_answer(hits) + f"\n\n（生成失败：{exc}）"
                used_llm = False
        else:
            answer = extractive_answer(hits)
        return {
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "used_llm": used_llm,
            "mode": self.mode,
            "top_k": self.top_k,
        }
