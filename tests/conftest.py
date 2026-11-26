"""pytest 公共夹具。

- 把仓库根目录放进 sys.path，保证 api 和 src 都能导入
- 会话级 TestClient：整个接口测试只启动一次 FastAPI，索引只加载一次
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("RAG_INDEX", str(ROOT / "data" / "index"))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as test_client:
        health = test_client.get("/health")
        assert health.status_code == 200, (
            "索引未就绪，先在仓库根目录执行 python scripts/build_index.py；"
            f"health={health.text}"
        )
        yield test_client
