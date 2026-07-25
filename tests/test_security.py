"""SnapPrint 安全 / 批量 / 模型动物园 测试。"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as M
from app.main import app

client = TestClient(app)


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (48, 48), (200, 80, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_models_list():
    """/api/models 返回模型动物园，含垂类与可用标注。"""
    r = client.get("/api/models")
    assert r.status_code == 200, r.text
    models = r.json()["models"]
    assert any(m["id"] == "hunyuan3d" for m in models)
    assert any(m["domain"] == "手办" for m in models)
    assert all("weights" in m and "backend" in m for m in models)


def _poll(tid, limit=120):
    """轮询任务直到完成；上限 120 次 × 0.3s ≈ 36s，兼容全量套件下的资源争用。"""
    for _ in range(limit):
        t = client.get(f"/api/tasks/{tid}").json()
        if t["status"] in ("done", "error"):
            return t
        import time
        time.sleep(0.3)
    return t


def test_batch():
    """批量上传多图 → 各自任务 → 全部完成。"""
    png = _png()
    files = [
        ("files", ("a.png", png, "image/png")),
        ("files", ("b.png", png, "image/png")),
    ]
    r = client.post("/api/batch", files=files, data={"mode": "relief"})
    assert r.status_code == 200, r.text
    ids = r.json()["task_ids"]
    assert len(ids) == 2
    for tid in ids:
        assert _poll(tid)["status"] == "done"


def test_model_field_relief_ignored():
    """离线浮雕模式忽略 model（垂类），仍正常生成。"""
    r = client.post(
        "/api/generate_async",
        files={"file": ("t.png", _png(), "image/png")},
        data={"mode": "relief", "model": "figure"},
    )
    assert r.status_code == 200
    assert _poll(r.json()["task_id"])["status"] == "done"


def test_rate_limit(monkeypatch):
    """启用限流后，超过阈值返回 429（用 monkeypatch 隔离，不污染全局）。"""
    monkeypatch.setattr(M, "RATE_LIMIT", 2)
    files = {"file": ("t.png", _png(), "image/png")}
    client.post("/api/generate", files=files, data={"mode": "relief"})
    client.post("/api/generate", files=files, data={"mode": "relief"})
    r3 = client.post("/api/generate", files=files, data={"mode": "relief"})
    assert r3.status_code == 429
