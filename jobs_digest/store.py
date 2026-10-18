"""SQLite memory of what has been seen and what has been sent, per channel. This is what makes runs idempotent."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .scoring import Scored

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    key        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    company    TEXT NOT NULL,
    url        TEXT NOT NULL,
    score      REAL NOT NULL,
    first_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sent (
    key     TEXT NOT NULL,
    channel TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (key, channel)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    """One small SQLite file. Use as a context manager so the connection is closed."""

    def __init__(self, path: str | Path = "digest.sqlite"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def remember(self, items: list[Scored], when: str | None = None) -> int:
        """Record postings the first time they are seen. Returns how many were new to the store."""
        when = when or _now()
        rows = [(s.posting.key, s.posting.title, s.posting.company, s.posting.url, s.score, when) for s in items]
        before = self.conn.total_changes
        self.conn.executemany("INSERT OR IGNORE INTO postings VALUES (?, ?, ?, ?, ?, ?)", rows)
        self.conn.commit()
        return self.conn.total_changes - before

    def unsent(self, items: list[Scored], channel: str) -> list[Scored]:
        """Keep only the items this channel has not received yet, preserving order."""
        if not items:
            return []
        placeholders = ",".join("?" for _ in items)
        rows = self.conn.execute(
            f"SELECT key FROM sent WHERE channel = ? AND key IN ({placeholders})",
            [channel, *(s.posting.key for s in items)],
        ).fetchall()
        done = {r[0] for r in rows}
        return [s for s in items if s.posting.key not in done]

    def mark_sent(self, items: list[Scored], channel: str, when: str | None = None) -> None:
        when = when or _now()
        self.conn.executemany(
            "INSERT OR IGNORE INTO sent VALUES (?, ?, ?)", [(s.posting.key, channel, when) for s in items]
        )
        self.conn.commit()

    def stats(self) -> dict[str, int]:
        postings = self.conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
        sent = self.conn.execute("SELECT COUNT(*) FROM sent").fetchone()[0]
        return {"postings": postings, "sent": sent}
