"""服务配置：全部来自环境变量，方便容器与 CI 覆盖。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

VERSION = "0.1.0"
MODES = ("hybrid", "bm25", "vector")


def _int_env(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(low, min(high, value))


def _mode_env(name: str, default: str) -> str:
    raw = os.environ.get(name, "").strip().lower()
    return raw if raw in MODES else default


@dataclass(frozen=True)
class Settings:
    index_dir: Path
    default_top_k: int = 5
    default_mode: str = "hybrid"
    max_question_chars: int = 2000
    version: str = VERSION
    calendar_path: Path = Path("data/calendar/semester.json")
    agent_max_steps: int = 2


def load_settings() -> Settings:
    """每次启动读一次，测试里可以直接构造 Settings 覆盖。"""
    return Settings(
        index_dir=Path(os.environ.get("RAG_INDEX", "data/index")),
        default_top_k=_int_env("RAG_TOP_K", 5, 1, 10),
        default_mode=_mode_env("RAG_MODE", "hybrid"),
        max_question_chars=_int_env("RAG_MAX_QUESTION_CHARS", 2000, 1, 20000),
        calendar_path=Path(os.environ.get("AGENT_CALENDAR", "data/calendar/semester.json")),
        agent_max_steps=_int_env("AGENT_MAX_STEPS", 2, 1, 3),
    )
