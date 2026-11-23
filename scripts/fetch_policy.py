# -*- coding: utf-8 -*-
"""抓取公开政策网页并转成 Markdown（仅标准库）。"""
from __future__ import annotations
import html as htmllib
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


class BlockParser(HTMLParser):
    """收集 <h1-4>、<p> 的文本，按块输出。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.blocks: list[tuple[str, str]] = []
        self.buf: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self.skip += 1
            return
        if tag in ("h1", "h2", "h3", "h4", "p", "li", "td"):
            self.stack.append(tag)
            self.buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        if tag in ("h1", "h2", "h3", "h4", "p", "li", "td") and self.stack:
            while self.stack:
                cur = self.stack.pop()
                text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
                self.buf = []
                if text and not self.skip:
                    self.blocks.append((cur, text))
                if cur == tag:
                    break

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.buf.append(data)


def decode(raw: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if m:
        try:
            return raw.decode(m.group(1), errors="ignore")
        except LookupError:
            pass
    head = raw[:3000].decode("ascii", errors="ignore")
    m = re.search(r"charset=[\"']?([\w-]+)", head, re.I)
    if m:
        try:
            return raw.decode(m.group(1), errors="ignore")
        except LookupError:
            pass
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


NAV_NOISE = ("首页", "上一页", "下一页", "打印", "关闭", "返回", "分享到", "扫一扫", "网站地图",
             "主办单位", "版权所有", "ICP备", "公网安备", "网站标识码", "点击量", "字号")


def clean_blocks(blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tag, text in blocks:
        if len(text) < 8:
            continue
        if any(n in text for n in NAV_NOISE) and len(text) < 120:
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append((tag, text))
    return out


def to_markdown(title: str, blocks: list[tuple[str, str]]) -> str:
    lines = [f"# {title}", ""]
    for tag, text in blocks:
        if tag in ("h1", "h2", "h3", "h4"):
            lines.append(f"## {text}")
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    jobs = [
        ("01-普通高等学校学生管理规定.md", "普通高等学校学生管理规定（教育部令第41号）",
         "http://www.moe.gov.cn/jyb_xxgk/xxgk/zhengce/guizhang/202112/t20211206_585064.html"),
        ("02-安徽省家庭经济困难学生认定工作实施办法.md", "安徽省家庭经济困难学生认定工作实施办法",
         "https://www.ahhuoshan.gov.cn/public/6626822/36881734.html"),
        ("03-学生资助政策14项.md", "高校学生资助政策（14 项）",
         "https://www.bengbu.gov.cn/ywdt/ztzl/rdzt/zcjmwd/jfjs/51070454.html"),
    ]
    outdir = Path("data/docs")
    outdir.mkdir(parents=True, exist_ok=True)
    for name, title, url in jobs:
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                ctype = resp.headers.get("Content-Type", "")
            text = decode(raw, ctype)
            parser = BlockParser()
            parser.feed(text)
            blocks = clean_blocks(parser.blocks)
            md = to_markdown(title, blocks)
            (outdir / name).write_text(md, encoding="utf-8")
            print(f"OK {name}  bytes={len(raw)}  chars={len(md)}  blocks={len(blocks)}")
            print("   前 120 字：", re.sub(r"\s+", " ", md)[:120])
        except Exception as exc:
            print(f"FAIL {name}: {exc}")


if __name__ == "__main__":
    main()
