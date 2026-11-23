"""RAG 主流程：检索 -> 句级重排 -> 拼上下文 -> 生成（无 API Key 时降级抽取式）。"""
from __future__ import annotations

import re
import time

from . import llm
from .embedder import load_embedder
from .index import RagIndex
from .query import expand
from .text import tokenize

SYSTEM_PROMPT = (
    "你是一名严谨的高校政策助手。只能依据【参考资料】回答，不得编造。"
    "回答时用 [1][2] 这样的编号标注引用来源；如果资料不足以回答，直接说明"
    "“根据现有资料无法确定”，并指出还缺什么信息。用简体中文回答，控制在 300 字以内。"
)

_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]


def usable_sentences(text: str) -> list[str]:
    """可用于摘录的句子：去掉标题行、章节名和过短的句子。"""
    out = []
    for s in split_sentences(text):
        s = s.strip().lstrip("#").strip()
        if len(s) < 12:
            continue
        if re.match(r"^第[一二三四五六七八九十百]+[章节条]", s) and len(s) < 20:
            continue
        out.append(s)
    return out or split_sentences(text)


def best_snippet(text: str, question: str, max_len: int = 180) -> str:
    """在切片里挑与问题最相关的一句，避免摘录总是从切片开头截。"""
    sentences = usable_sentences(text)
    if not sentences:
        return (text or "").strip()[:max_len]
    q_tokens = set(tokenize(expand(question)))
    best = max(sentences, key=lambda s: len(q_tokens & set(tokenize(s))))
    if len(best) > max_len:
        best = best[:max_len] + "…"
    return best


def rerank_by_sentence(hits: list[dict], question: str, top_k: int, idf: dict[str, float]) -> list[dict]:
    """句级重排：用“切片内最佳句（含标题前缀）的 IDF 加权词重合度”重排候选。

    政策文本里“名额”“6000 元”这类词区分度很高，用 IDF 加权能压过
    “每生每年”“万元”这种到处都有的词，避免挑到语义相近但答非所问的句子。
    """
    q_tokens = set(tokenize(expand(question)))
    scored = []
    for h in hits:
        text = h["chunk"].text
        heading = text.splitlines()[0] if text else ""
        sentence = best_snippet(text, question, max_len=400)
        weight = sum(idf.get(t, 0.0) for t in q_tokens & set(tokenize(heading + " " + sentence)))
        scored.append((weight, -h["rank"], h))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [h for _, _, h in scored[:top_k]]


def build_prompt(question: str, hits: list[dict]) -> str:
    lines = [f"【问题】{question}", "", "【参考资料】"]
    for i, hit in enumerate(hits, start=1):
        chunk = hit["chunk"]
        lines.append(f"[{i}] 来源：{chunk.doc_id}（块 {chunk.index}）")
        lines.append(chunk.text)
        lines.append("")
    lines.append("请依据以上资料作答，并标注引用编号。")
    return "\n".join(lines)


def extractive_answer(question: str, hits: list[dict], limit: int = 3) -> str:
    if not hits:
        return "没有检索到相关资料，建议换个问法，或把相关文档加入知识库。"
    parts = []
    for i, hit in enumerate(hits[:limit], start=1):
        chunk = hit["chunk"]
        parts.append(f"[{i}] {best_snippet(chunk.text, question)}（来源：{chunk.doc_id}）")
    return "（当前未配置大模型 API，以下为检索到的原文摘录）\n" + "\n".join(parts)


class RagPipeline:
    def __init__(self, index: RagIndex, top_k: int = 5, mode: str = "hybrid") -> None:
        self.index = index
        self.top_k = top_k
        self.mode = mode
        self.embedder = load_embedder()

    def ask(self, question: str) -> dict:
        started = time.perf_counter()
        # 多召回一些候选，再做句级重排，避免精确答案因排序靠后而被丢掉
        candidates = self.index.search(
            question, top_k=max(self.top_k * 3, 15), mode=self.mode, embedder=self.embedder
        )
        hits = rerank_by_sentence(candidates, question, self.top_k, self.index.bm25.idf)
        contexts = [
            {
                "id": i + 1,
                "doc_id": h["chunk"].doc_id,
                "title": h["chunk"].title,
                "chunk_index": h["chunk"].index,
                "score": round(h["score"], 4),
                "snippet": best_snippet(h["chunk"].text, question),
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
                answer = extractive_answer(question, hits) + f"\n\n（生成失败：{exc}）"
                used_llm = False
        else:
            answer = extractive_answer(question, hits)
        return {
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "used_llm": used_llm,
            "mode": self.mode,
            "top_k": self.top_k,
        }
