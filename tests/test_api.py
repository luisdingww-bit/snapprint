"""SnapPrint API 冒烟测试：异步任务队列 + 同步接口兼容。"""
from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)


def _png() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (96, 96), (200, 80, 40))
    # 加点横向渐变，让浮雕生成有意义
    px = img.load()
    for y in range(96):
        for x in range(96):
            px[x, y] = (int(255 * x / 96), 80, 40)
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_generate_async_pipeline():
    """提交 -> 轮询 -> 完成：异步任务队列端到端可用。"""
    data = _png()
    r = client.post(
        "/api/generate_async",
        files={"file": ("t.png", data, "image/png")},
        data={"mode": "relief"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "task_id" in body, body

    tid = body["task_id"]
    # 首次轮询应处于排队/运行/已完成之一（离线浮雕极快，可能已 done）
    first = client.get(f"/api/tasks/{tid}").json()
    assert first["status"] in ("queued", "running", "done"), first
    deadline = time.time() + 120
    final = None
    while time.time() < deadline:
        t = client.get(f"/api/tasks/{tid}").json()
        if t["status"] in ("done", "error"):
            final = t
            break
        time.sleep(0.3)
    assert final is not None, "任务在 120s 内未完成"
    assert final["status"] == "done", final.get("error")
    assert final["result"]["stats"]["watertight"] is True
    assert "obj" in final["result"]["files"]


def test_task_404():
    """未知 task_id 返回 404。"""
    assert client.get("/api/tasks/does_not_exist").status_code == 404


def test_sync_generate_compat():
    """原有同步接口向后兼容，仍直接返回结果。"""
    data = _png()
    r = client.post(
        "/api/generate",
        files={"file": ("t.png", data, "image/png")},
        data={"mode": "relief"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["watertight"] is True
