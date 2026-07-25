"""SnapPrint 社区数据层（零依赖 SQLite）。

存储用户上传的模型「提交」+ 可打印性分析报告 + 社区评论。
数据库文件位于 data/snapprint.db；上传的模型原文件存于 outputs/uploads/。
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
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
        CREATE INDEX IF NOT EXISTS idx_sub_created ON submissions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_com_sub ON comments(submission_id);
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
