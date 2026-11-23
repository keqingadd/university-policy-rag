"""文本处理：中文/英文分词、文档加载、切片。"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_LATIN_RE = re.compile(r"[a-zA-Z0-9_+#.]+")
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
SUPPORTED_SUFFIX = {".md", ".markdown", ".txt"}


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


def tokenize(text: str) -> list[str]:
    """混合分词：英文/数字用整词，中文用 2-gram + 3-gram（对中文检索很稳）。"""
    t = normalize(text).lower()
    tokens: list[str] = []
    for w in _LATIN_RE.findall(t):
        if len(w) >= 2:
            tokens.append(w)
    for run in _CJK_RE.findall(t):
        chars = list(run)
        if len(chars) == 1:
            tokens.append(chars[0])
            continue
        for i in range(len(chars) - 1):
            tokens.append(chars[i] + chars[i + 1])
        for i in range(len(chars) - 2):
            tokens.append(chars[i] + chars[i + 1] + chars[i + 2])
    return tokens


@dataclass
class Chunk:
    doc_id: str
    title: str
    index: int
    text: str


def _split_sentences(block: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(block)]
    return [p for p in parts if p]


def _split_long(block: str, limit: int = 300) -> list[str]:
    out: list[str] = []
    for sent in _split_sentences(block) or [block]:
        while len(sent) > limit:
            out.append(sent[:limit])
            sent = sent[limit:]
        if sent:
            out.append(sent)
    return out


def _sections(text: str) -> list[tuple[str, str]]:
    """按 Markdown 标题切段：返回 [(heading, body)]，保留段内换行。"""
    sections: list[tuple[str, str]] = []
    heading = ""
    body: list[str] = []

    def flush() -> None:
        nonlocal body
        joined = "\n".join(body).strip()
        if joined or heading:
            sections.append((heading, joined))
        body = []

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            heading = m.group(2).strip()
            body = []
        else:
            body.append(line)
    flush()
    return [(h, b) for h, b in sections if b or h]


def chunk_text(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """标题感知切片：每个二级标题尽量独立成块，长段再按句子切并带标题前缀。"""
    chunks: list[str] = []
    for heading, body in _sections(text):
        prefix = (heading + "\n") if heading else ""
        if not body:
            continue
        if len(prefix) + len(body) <= size:
            chunks.append((prefix + body).strip())
            continue
        sentences = _split_long(body)
        buf = ""
        for sent in sentences:
            if buf and len(prefix) + len(buf) + len(sent) > size:
                chunks.append((prefix + buf).strip())
                keep: list[str] = []
                total = 0
                for prev in reversed(_split_sentences(buf)):
                    if total + len(prev) > overlap:
                        break
                    keep.insert(0, prev)
                    total += len(prev)
                buf = "".join(keep) + sent
            else:
                buf += sent
        if buf.strip():
            chunks.append((prefix + buf).strip())
    return chunks


def _guess_title(raw: str, fallback: str) -> str:
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip() or fallback
        if line:
            return line[:40]
    return fallback


def load_documents(docs_dir: str | Path) -> list[tuple[str, str, str]]:
    """返回 [(doc_id, title, raw_text)]，按文件名排序，保证索引可复现。"""
    root = Path(docs_dir)
    if not root.exists():
        raise FileNotFoundError(f"文档目录不存在: {root}")
    docs: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIX:
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        docs.append((path.relative_to(root).as_posix(), _guess_title(raw, path.stem), raw))
    return docs
