"""SnapPrint 社区数据层（零依赖 SQLite）。

存储用户上传的模型「提交」+ 可打印性分析报告 + 社区评论。
数据库文件位于 data/snapprint.db；上传的模型原文件存于 outputs/uploads/。
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 数据目录可经 SNAPRINT_DATA_DIR 覆盖（部署到 Railway / 容器时挂持久卷到该路径）。
_DATA_DIR_ENV = (os.environ.get("SNAPRINT_DATA_DIR") or "").strip()
DATA_DIR = Path(_DATA_DIR_ENV) if _DATA_DIR_ENV else (ROOT / "data")
DB_PATH = DATA_DIR / "snapprint.db"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init() -> None:
    """建表（幂等）。"""
    c = _connect()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id          TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            author      TEXT DEFAULT '匿名',
            ext         TEXT,
            size_bytes  INTEGER DEFAULT 0,
            model_path  TEXT,
            report_json TEXT,
            score       INTEGER DEFAULT 0,
            created_at  REAL
        );
        CREATE TABLE IF NOT EXISTS comments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT NOT NULL,
            author        TEXT DEFAULT '匿名',
            body          TEXT NOT NULL,
            created_at    REAL,
            FOREIGN KEY(submission_id) REFERENCES submissions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ratings (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT NOT NULL,
            author        TEXT NOT NULL,
            stars         INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 5),
            review        TEXT NOT NULL,
            created_at    REAL,
            UNIQUE(submission_id, author),
            FOREIGN KEY(submission_id) REFERENCES submissions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_sub_created ON submissions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_com_sub ON comments(submission_id);
        CREATE INDEX IF NOT EXISTS idx_rate_sub ON ratings(submission_id);
        """
    )
    c.commit()
    c.close()


def add_submission(
    *,
    sid: str,
    filename: str,
    author: str,
    ext: str,
    size_bytes: int,
    model_path: str,
    report: dict,
) -> None:
    init()
    c = _connect()
    c.execute(
        """
        INSERT INTO submissions
            (id, filename, author, ext, size_bytes, model_path, report_json, score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sid,
            filename,
            author or "匿名",
            ext,
            size_bytes,
            model_path,
            json.dumps(report, ensure_ascii=False),
            int(report.get("score", 0)),
            time.time(),
        ),
    )
    c.commit()
    c.close()


def list_submissions(limit: int = 24, offset: int = 0) -> tuple[list[dict], int]:
    init()
    c = _connect()
    rows = c.execute(
        """
        SELECT s.id, s.filename, s.author, s.ext, s.size_bytes, s.score, s.created_at,
               (SELECT COUNT(*) FROM comments c WHERE c.submission_id = s.id) AS comments
        FROM submissions s ORDER BY created_at DESC LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    total = c.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    c.close()
    return [dict(r) for r in rows], total


def get_submission(sid: str) -> dict | None:
    init()
    c = _connect()
    r = c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    c.close()
    if not r:
        return None
    d = dict(r)
    d["report"] = json.loads(d.pop("report_json"))
    return d


def add_comment(*, sid: str, author: str, body: str) -> int:
    init()
    c = _connect()
    cur = c.execute(
        "INSERT INTO comments (submission_id, author, body, created_at) VALUES (?, ?, ?, ?)",
        (sid, author or "匿名", body, time.time()),
    )
    cid = cur.lastrowid
    c.commit()
    c.close()
    return cid


def list_comments(sid: str) -> list[dict]:
    init()
    c = _connect()
    rows = c.execute(
        """
        SELECT id, author, body, created_at
        FROM comments WHERE submission_id=? ORDER BY created_at ASC
        """,
        (sid,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def count_comments(sid: str) -> int:
    init()
    c = _connect()
    n = c.execute(
        "SELECT COUNT(*) FROM comments WHERE submission_id=?", (sid,)
    ).fetchone()[0]
    c.close()
    return n


# ---------------------------------------------------------------------------
# 社区评分（用户星级 + 文字评价；每作者对同一作品限评一次，重复提交覆盖）
# ---------------------------------------------------------------------------
def add_rating(*, sid: str, author: str, stars: int, review: str) -> None:
    """提交/更新某作者对该作品的评分（UNIQUE(submission_id,author) 自动 upsert）。"""
    init()
    c = _connect()
    c.execute(
        """
        INSERT INTO ratings (submission_id, author, stars, review, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(submission_id, author) DO UPDATE SET
            stars=excluded.stars, review=excluded.review, created_at=excluded.created_at
        """,
        (sid, author, int(stars), review, time.time()),
    )
    c.commit()
    c.close()


def get_rating_stats(sid: str) -> dict:
    """某作品的评分聚合：计数、均值、星级分布（含每星人数）。"""
    init()
    c = _connect()
    rows = c.execute(
        "SELECT stars, COUNT(*) AS n FROM ratings WHERE submission_id=? GROUP BY stars",
        (sid,),
    ).fetchall()
    c.close()
    dist = {str(k): 0 for k in (5, 4, 3, 2, 1)}
    total = 0
    ssum = 0
    for r in rows:
        s = int(r["stars"])
        n = int(r["n"])
        dist[str(s)] = n
        total += n
        ssum += s * n
    avg = round(ssum / total, 2) if total else 0.0
    return {"count": total, "avg": avg, "dist": dist}


def global_rating_stats() -> dict:
    """社区全局评分统计：总作品、总评价、全局平均评分、最活跃评价者。"""
    init()
    c = _connect()
    total_sub = c.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    total_rate = c.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
    row = c.execute("SELECT AVG(stars) AS m FROM ratings").fetchone()
    avg = round(row["m"], 2) if row["m"] is not None else 0.0
    top = c.execute(
        "SELECT author, COUNT(*) AS n FROM ratings GROUP BY author ORDER BY n DESC LIMIT 5"
    ).fetchall()
    c.close()
    return {
        "total_submissions": total_sub,
        "total_ratings": total_rate,
        "avg_rating": avg,
        "top_authors": [{"author": r["author"], "count": r["n"]} for r in top],
    }
