from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    youtube_video_id TEXT NOT NULL UNIQUE,
    channel_handle TEXT NOT NULL,
    title TEXT NOT NULL,
    youtube_url TEXT NOT NULL,
    published_at TEXT NOT NULL,
    duration_sec INTEGER NOT NULL DEFAULT 0,
    is_short INTEGER NOT NULL DEFAULT 0,
    local_video_path TEXT,
    local_audio_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    raw_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL UNIQUE,
    source TEXT NOT NULL,
    language TEXT,
    text TEXT NOT NULL,
    segments_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL UNIQUE,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    captures_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    destination TEXT NOT NULL,
    provider TEXT NOT NULL,
    external_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    last_error TEXT,
    sent_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(article_id) REFERENCES articles(id)
);

CREATE TABLE IF NOT EXISTS quality_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    score REAL,
    findings_json TEXT NOT NULL DEFAULT '[]',
    raw_response_json TEXT NOT NULL DEFAULT '{}',
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_run_at TEXT NOT NULL,
    last_error TEXT,
    lock_token TEXT,
    locked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class Repository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_video(
        self,
        *,
        youtube_video_id: str,
        channel_handle: str,
        title: str,
        youtube_url: str,
        published_at: str,
        duration_sec: int,
        is_short: bool,
        raw_json: Dict[str, Any],
        local_video_path: str | None = None,
        local_audio_path: str | None = None,
        status: str = "pending",
    ) -> int:
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM videos WHERE youtube_video_id = ?",
                (youtube_video_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE videos
                    SET title = ?, youtube_url = ?, published_at = ?, duration_sec = ?,
                        is_short = ?, raw_json = ?, local_video_path = COALESCE(?, local_video_path),
                        local_audio_path = COALESCE(?, local_audio_path), status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        title,
                        youtube_url,
                        published_at,
                        duration_sec,
                        int(is_short),
                        to_json(raw_json),
                        local_video_path,
                        local_audio_path,
                        status,
                        now,
                        existing["id"],
                    ),
                )
                return int(existing["id"])

            cur = conn.execute(
                """
                INSERT INTO videos (
                    youtube_video_id, channel_handle, title, youtube_url, published_at,
                    duration_sec, is_short, local_video_path, local_audio_path, status,
                    raw_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    youtube_video_id,
                    channel_handle,
                    title,
                    youtube_url,
                    published_at,
                    duration_sec,
                    int(is_short),
                    local_video_path,
                    local_audio_path,
                    status,
                    to_json(raw_json),
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def update_video_paths(self, video_id: int, *, local_video_path: str | None, local_audio_path: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE videos
                SET local_video_path = COALESCE(?, local_video_path),
                    local_audio_path = COALESCE(?, local_audio_path),
                    updated_at = ?
                WHERE id = ?
                """,
                (local_video_path, local_audio_path, utc_now(), video_id),
            )

    def get_video(self, video_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()

    def get_video_by_youtube_id(self, youtube_video_id: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM videos WHERE youtube_video_id = ?",
                (youtube_video_id,),
            ).fetchone()

    def list_videos(self) -> Iterable[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM videos ORDER BY published_at DESC, id DESC").fetchall())

    def save_transcript(
        self,
        *,
        video_id: int,
        source: str,
        language: str | None,
        text: str,
        segments: list[dict[str, Any]],
        status: str,
    ) -> int:
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM transcripts WHERE video_id = ?", (video_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE transcripts
                    SET source = ?, language = ?, text = ?, segments_json = ?, status = ?, updated_at = ?
                    WHERE video_id = ?
                    """,
                    (source, language, text, to_json(segments), status, now, video_id),
                )
                return int(existing["id"])

            cur = conn.execute(
                """
                INSERT INTO transcripts (
                    video_id, source, language, text, segments_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (video_id, source, language, text, to_json(segments), status, now, now),
            )
            return int(cur.lastrowid)

    def get_transcript(self, video_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM transcripts WHERE video_id = ?", (video_id,)).fetchone()

    def list_transcripts(self) -> Iterable[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM transcripts ORDER BY id ASC").fetchall())

    def save_article(
        self,
        *,
        video_id: int,
        headline: str,
        summary: str,
        body: str,
        sources: list[dict[str, Any]],
        captures: list[dict[str, Any]],
        status: str,
    ) -> int:
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM articles WHERE video_id = ?", (video_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE articles
                    SET headline = ?, summary = ?, body = ?, sources_json = ?, captures_json = ?,
                        status = ?, updated_at = ?
                    WHERE video_id = ?
                    """,
                    (
                        headline,
                        summary,
                        body,
                        to_json(sources),
                        to_json(captures),
                        status,
                        now,
                        video_id,
                    ),
                )
                return int(existing["id"])

            cur = conn.execute(
                """
                INSERT INTO articles (
                    video_id, headline, summary, body, sources_json, captures_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id,
                    headline,
                    summary,
                    body,
                    to_json(sources),
                    to_json(captures),
                    status,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def get_article(self, video_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM articles WHERE video_id = ?", (video_id,)).fetchone()

    def get_article_by_id(self, article_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()

    def list_articles(self) -> Iterable[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM articles ORDER BY id ASC").fetchall())

    def save_delivery(
        self,
        *,
        article_id: int,
        destination: str,
        provider: str,
        external_id: str | None,
        payload: dict[str, Any],
        status: str,
        last_error: str | None = None,
        sent_at: str | None = None,
    ) -> int:
        now = utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO deliveries (
                    article_id, destination, provider, external_id, payload_json, status,
                    last_error, sent_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article_id,
                    destination,
                    provider,
                    external_id,
                    to_json(payload),
                    status,
                    last_error,
                    sent_at,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def list_deliveries(self) -> Iterable[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM deliveries ORDER BY id ASC").fetchall())

    def save_quality_check(
        self,
        *,
        stage: str,
        entity_type: str,
        entity_id: int,
        status: str,
        findings: list[dict[str, Any]],
        score: float | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO quality_checks (
                    stage, entity_type, entity_id, status, score, findings_json, raw_response_json, checked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stage,
                    entity_type,
                    entity_id,
                    status,
                    score,
                    to_json(findings),
                    to_json(raw_response or {}),
                    utc_now(),
                ),
            )
            return int(cur.lastrowid)

    def enqueue_job(
        self,
        *,
        job_type: str,
        entity_type: str,
        entity_id: int,
        dedupe_key: str,
        payload: dict[str, Any] | None = None,
        delay_seconds: int = 0,
    ) -> int:
        now = datetime.now(timezone.utc)
        next_run_at = (now + timedelta(seconds=delay_seconds)).isoformat()
        created_at = now.isoformat()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM jobs WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            if existing:
                return int(existing["id"])

            cur = conn.execute(
                """
                INSERT INTO jobs (
                    job_type, entity_type, entity_id, dedupe_key, payload_json, status,
                    attempts, next_run_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
                """,
                (job_type, entity_type, entity_id, dedupe_key, to_json(payload or {}), next_run_at, created_at, created_at),
            )
            return int(cur.lastrowid)

    def claim_next_job(self, job_type: str | None = None) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if job_type:
                row = conn.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status = 'pending' AND job_type = ? AND next_run_at <= ?
                    ORDER BY next_run_at ASC, id ASC
                    LIMIT 1
                    """,
                    (job_type, utc_now()),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status = 'pending' AND next_run_at <= ?
                    ORDER BY next_run_at ASC, id ASC
                    LIMIT 1
                    """,
                    (utc_now(),),
                ).fetchone()
            if not row:
                return None

            token = str(uuid.uuid4())
            conn.execute(
                """
                UPDATE jobs
                SET status = 'running', attempts = attempts + 1, lock_token = ?, locked_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (token, utc_now(), utc_now(), row["id"]),
            )
            return conn.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone()

    def complete_job(self, job_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'success', updated_at = ?, lock_token = NULL, locked_at = NULL
                WHERE id = ?
                """,
                (utc_now(), job_id),
            )

    def fail_job(self, job_id: int, error: str, retry_delay_seconds: int = 300) -> None:
        next_run_at = (datetime.now(timezone.utc) + timedelta(seconds=retry_delay_seconds)).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'pending', last_error = ?, next_run_at = ?, updated_at = ?,
                    lock_token = NULL, locked_at = NULL
                WHERE id = ?
                """,
                (error, next_run_at, utc_now(), job_id),
            )

    def list_jobs(self) -> Iterable[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM jobs ORDER BY id ASC").fetchall())

    def set_entity_status(self, table: str, entity_id: int, status: str) -> None:
        if table not in {"videos", "transcripts", "articles", "deliveries"}:
            raise ValueError(f"Unsupported table: {table}")
        with self.connect() as conn:
            conn.execute(
                f"UPDATE {table} SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), entity_id),
            )
