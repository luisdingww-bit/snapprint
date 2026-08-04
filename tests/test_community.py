"""SnapPrint 社区版端到端测试：上传分析 → 画廊 → 详情 → 评论。

用 tmp_path 隔离 SQLite 与上传目录，避免污染仓库。
"""
from __future__ import annotations

import io

import pytest
import trimesh
from fastapi.testclient import TestClient

from app import db, main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "snapprint.db")
    up = tmp_path / "uploads"
    up.mkdir(exist_ok=True)
    monkeypatch.setattr(main, "UPLOADS", up)
    db.init()
    yield TestClient(main.app)


def _stl(mesh) -> bytes:
    buf = io.BytesIO()
    mesh.export(buf, file_type="stl")
    return buf.getvalue()


def test_upload_then_gallery(client):
    data = _stl(trimesh.creation.box(extents=(40, 30, 20)))
    r = client.post(
        "/api/upload",
        files={"file": ("a.stl", data, "application/octet-stream")},
        data={"author": "X", "printer": "bambu_a1", "material": "pla"},
    )
    assert r.status_code == 200
    sid = r.json()["id"]
    assert 0 <= r.json()["score"] <= 100

    g = client.get("/api/gallery").json()
    assert g["total"] == 1
    assert g["items"][0]["id"] == sid
    assert g["items"][0]["comments"] == 0


def test_detail_and_comments(client):
    data = _stl(trimesh.creation.box())
    sid = client.post(
        "/api/upload", files={"file": ("b.stl", data, "application/octet-stream")}
    ).json()["id"]

    c1 = client.post(
        f"/api/models/{sid}/comments",
        data={"author": "Y", "body": "水密不错"},
    )
    assert c1.status_code == 200

    d = client.get(f"/api/models/{sid}").json()
    assert len(d["comments"]) == 1
    assert d["comments"][0]["body"] == "水密不错"
    assert d["submission"]["report"]["watertight"] is True


def test_empty_comment_rejected(client):
    data = _stl(trimesh.creation.box())
    sid = client.post(
        "/api/upload", files={"file": ("b.stl", data, "application/octet-stream")}
    ).json()["id"]
    r = client.post(f"/api/models/{sid}/comments", data={"body": "   "})
    assert r.status_code == 400


def test_bad_format_rejected(client):
    r = client.post(
        "/api/upload", files={"file": ("x.png", b"fake", "image/png")}
    )
    assert r.status_code == 400


def test_presets_and_scoreboard(client):
    data = _stl(trimesh.creation.box())
    client.post(
        "/api/upload", files={"file": ("b.stl", data, "application/octet-stream")}
    )
    p = client.get("/api/presets").json()
    assert len(p["printers"]) >= 1 and len(p["materials"]) >= 1
    sb = client.get("/api/scoreboard").json()
    assert sb["items"][0]["score"] >= 0


def test_scoreboard_community_handles_unrated_models(client):
    """社区榜存在 0 评分模型时不应 500（回归：None 参与 sorted 会抛 TypeError）。"""
    for name in ("a.stl", "b.stl"):
        data = _stl(trimesh.creation.box(extents=(40, 30, 20)))
        r = client.post(
            "/api/upload", files={"file": (name, data, "application/octet-stream")}
        )
        assert r.status_code == 200
    r = client.get("/api/scoreboard?sort=community")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    assert all(it["community_rating"] is None for it in items)


def test_guard_api_key(client, monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "secret")
    data = _stl(trimesh.creation.box())
    f = {"file": ("b.stl", data, "application/octet-stream")}

    r1 = client.post("/api/upload", files=f)
    assert r1.status_code == 401

    r2 = client.post("/api/upload", files=f, headers={"X-API-Key": "secret"})
    assert r2.status_code == 200


def test_guard_rate_limit(client, monkeypatch):
    monkeypatch.setattr(main, "RATE_LIMIT", 1)
    data = _stl(trimesh.creation.box())
    f = {"file": ("b.stl", data, "application/octet-stream")}
    assert client.post("/api/upload", files=f).status_code == 200
    # 同一匿名客户端第二发给 429
    assert client.post("/api/upload", files=f).status_code == 429
