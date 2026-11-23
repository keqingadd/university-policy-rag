"""大模型调用：OpenAI 兼容 /chat/completions，零第三方依赖（urllib）。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def is_configured() -> bool:
    return bool(os.environ.get("LLM_API_KEY", "").strip())


def base_url() -> str:
    return os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")


def model_name() -> str:
    return os.environ.get("LLM_MODEL", "deepseek-chat")


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 900, timeout: int = 90) -> str:
    key = os.environ.get("LLM_API_KEY", "").strip()
    if not key:
        raise RuntimeError("未配置 LLM_API_KEY")
    body = json.dumps(
        {"model": model_name(), "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    ).encode("utf-8")
    req = urllib.request.Request(
        base_url() + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"LLM 接口 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM 接口网络错误: {exc.reason}") from exc
    return (payload["choices"][0]["message"]["content"] or "").strip()
