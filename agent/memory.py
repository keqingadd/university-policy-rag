"""多轮会话记忆：按 session_id 保存最近若干轮，进程内有效。"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict


class SessionMemory:
    def __init__(self, max_turns: int = 20) -> None:
        if max_turns < 1:
            raise ValueError("max_turns 至少为 1")
        self.max_turns = max_turns
        self._sessions: "OrderedDict[str, list[dict]]" = OrderedDict()
        self._lock = threading.Lock()

    def add(self, session_id: str, role: str, content: str, meta: dict | None = None) -> dict:
        turn = {"role": role, "content": content, "ts": time.time(), "meta": meta or {}}
        with self._lock:
            turns = self._sessions.setdefault(session_id, [])
            turns.append(turn)
            if len(turns) > self.max_turns:
                del turns[: len(turns) - self.max_turns]
            self._sessions.move_to_end(session_id)
            return turn

    def history(self, session_id: str) -> list[dict]:
        with self._lock:
            return list(self._sessions.get(session_id, []))

    def recent_text(self, session_id: str, turns: int = 2) -> str:
        items = self.history(session_id)[-turns * 2 :]
        return "\n".join(f"{item['role']}: {item['content'][:200]}" for item in items)

    def clear(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def stats(self) -> dict:
        with self._lock:
            return {"sessions": len(self._sessions), "max_turns": self.max_turns}
