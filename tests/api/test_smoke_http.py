"""真实 HTTP 冒烟：起一个 uvicorn 子进程，用 httpx 打真实端口。

进程内 TestClient 不经过网络栈，这条用例补上"真的能对外服务"的证据，
CI 和 Docker 里都会跑。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


# 本机环境可能开着系统代理（注册表 ProxyEnable=1），httpx 默认 trust_env=True
# 会把发往 127.0.0.1 的请求塞进代理，导致健康检查永远连不上。
CLIENT = httpx.Client(trust_env=False, timeout=10.0)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    port = int(os.environ.get("RAG_TEST_PORT", _free_port()))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("RAG_INDEX", str(ROOT / "data" / "index"))
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
            pytest.fail("uvicorn 提前退出：" + str(out))
        try:
            if CLIENT.get(f"{base}/health", timeout=1.0).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("uvicorn 30 秒内没有就绪")

    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.api
@pytest.mark.live
def test_live_health_and_query(live_server):
    health = CLIENT.get(f"{live_server}/health", timeout=5.0)
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    response = CLIENT.post(
        f"{live_server}/query",
        json={"question": "家庭经济困难学生认定多久评一次？"},
        timeout=10.0,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "每学年" in body["answer"]
    assert body["contexts"]
    assert response.headers["X-Request-ID"]


@pytest.mark.api
@pytest.mark.live
def test_live_error_contract(live_server):
    response = CLIENT.post(f"{live_server}/query", json={"question": " "}, timeout=5.0)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_QUESTION"
