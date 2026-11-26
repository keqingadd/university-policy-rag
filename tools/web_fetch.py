"""工具 3：抓取一个网页并抽正文（给“看官网最新通知”这类问题用）。

安全边界：只允许 http/https；拒绝 localhost 与内网地址；限制超时与字节数；
默认忽略系统代理（Windows 上代理常把本机请求劫走）。
"""
from __future__ import annotations

import html
import ipaddress
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .registry import Tool, ToolError

KEYWORDS = ("官网", "网址", "链接", "网页", "通知", "公告", "抓取", "打开", "这个页面", "原文")

PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "minLength": 8, "maxLength": 2048, "description": "要抓取的 http(s) 地址"},
        "max_chars": {"type": "integer", "minimum": 200, "maximum": 4000, "description": "正文最多返回多少字符"},
    },
    "required": ["url"],
    "additionalProperties": False,
}

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")

# 常见内网/本机地址前缀，直接拒绝（SSRF 的基本防护）
_PRIVATE_PREFIXES = ("localhost", "127.", "0.0.0.0", "10.", "192.168.", "169.254.", "::1", "[::1]")


def _is_private_host(host: str) -> bool:
    host = (host or "").strip().lower()
    if not host:
        return True
    if host.startswith(_PRIVATE_PREFIXES):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def clean_html(raw: str, max_chars: int) -> tuple[str, str, bool]:
    title_match = _TITLE_RE.search(raw)
    title = html.unescape(_TAG_RE.sub("", title_match.group(1))).strip() if title_match else ""
    body = _SCRIPT_RE.sub(" ", raw)
    body = _TAG_RE.sub(" ", body)
    body = html.unescape(body)
    body = _WS_RE.sub(" ", body)
    body = _NL_RE.sub("\n\n", body)
    text = "\n".join(line.strip() for line in body.splitlines() if line.strip())
    if title and text.startswith(title):
        text = text[len(title):].strip()
    truncated = len(text) > max_chars
    return title, text[:max_chars], truncated


def _default_fetch(url: str, timeout: float, max_bytes: int) -> dict:
    # ProxyHandler({}) = 明确不用任何代理（trust_env=False 的 urllib 版）
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, headers={"User-Agent": "policy-agent/0.1 (+https://github.com/keqingadd/university-policy-rag)"})
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(max_bytes + 1)
        charset = response.headers.get_content_charset() or "utf-8"
        final_url = response.geturl()
        status = response.status
    return {
        "url": final_url,
        "status": status,
        "content_type": response.headers.get("Content-Type", ""),
        "bytes": len(raw),
        "body": raw.decode(charset, errors="replace"),
    }


def web_fetch_tool(
    fetcher: Callable[[str, float, int], dict] | None = None,
    timeout: float = 6.0,
    max_bytes: int = 300_000,
) -> Tool:
    fetch = fetcher or _default_fetch

    def handler(args: dict) -> dict:
        url = args["url"].strip()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ToolError("FORBIDDEN_URL", "只支持 http/https 且必须是完整地址")
        if _is_private_host(parsed.hostname):
            raise ToolError("FORBIDDEN_URL", f"不允许访问内网或本机地址：{parsed.hostname}")
        try:
            fetched = fetch(url, timeout, max_bytes)
        except urllib.error.HTTPError as exc:
            raise ToolError("FETCH_FAILED", f"抓取失败：HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ToolError("FETCH_FAILED", f"抓取失败：{exc}") from exc

        max_chars = int(args.get("max_chars") or 800)
        title, text, truncated = clean_html(fetched["body"], max_chars)
        if not text.strip():
            raise ToolError("FETCH_EMPTY", "页面没有可读正文（可能是纯 JS 渲染）")
        return {
            "url": fetched["url"],
            "status": fetched["status"],
            "content_type": fetched.get("content_type", ""),
            "title": title,
            "text": text,
            "truncated": truncated,
            "bytes": fetched.get("bytes", len(fetched["body"])),
        }

    return Tool(
        name="web_fetch",
        description="抓取指定网页并抽取正文（用于查看学校官网通知等站外页面）。",
        parameters=PARAMETERS,
        handler=handler,
        keywords=KEYWORDS,
    )
