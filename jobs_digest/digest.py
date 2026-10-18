"""Build the digest and render it as plain text (terminal, email body), Telegram HTML and email HTML."""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import date

from .scoring import Scored

TELEGRAM_LIMIT = 4096


@dataclass
class Digest:
    date: str
    items: list[Scored]
    scanned: int = 0  # postings loaded from the input
    matched: int = 0  # postings that passed the profile (before the store and max_items)
    title: str = "Jobs digest"

    @property
    def headline(self) -> str:
        n = len(self.items)
        return (f"{self.title} {self.date}: {n} new match{'es' if n != 1 else ''} "
                f"({self.scanned} postings scanned, {self.matched} matched your profile)")


def build_digest(items: list[Scored], scanned: int, matched: int, today: date | None = None,
                 title: str = "Jobs digest") -> Digest:
    return Digest(date=(today or date.today()).isoformat(), items=list(items), scanned=scanned, matched=matched,
                  title=title)


def _meta(s: Scored) -> str:
    p = s.posting
    parts = [p.company, p.source, p.posted_at, p.location, p.salary]
    return " · ".join(x for x in parts if x)


def _score_line(s: Scored) -> str:
    n = int(s.score) if float(s.score).is_integer() else f"{s.score:g}"
    return f"score {n}: " + ", ".join(s.reasons) if s.reasons else f"score {n}"


def format_text(d: Digest) -> str:
    lines = [d.headline, ""]
    if not d.items:
        lines.append("Nothing new today.")
    for i, s in enumerate(d.items, 1):
        lines.append(f"{i:>2}. {s.posting.title}")
        lines.append(f"    {_meta(s)}")
        lines.append(f"    {_score_line(s)}")
        lines.append(f"    {s.posting.url}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_telegram(d: Digest) -> str:
    """Telegram's HTML subset: b, i, a, code. Newlines are literal."""
    esc = html.escape
    lines = [f"<b>{esc(d.headline)}</b>", ""]
    if not d.items:
        lines.append("Nothing new today.")
    for i, s in enumerate(d.items, 1):
        p = s.posting
        lines.append(f"{i}. <a href=\"{esc(p.url, quote=True)}\">{esc(p.title)}</a>")
        lines.append(esc(_meta(s)))
        lines.append(f"<i>{esc(_score_line(s))}</i>")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_email_html(d: Digest) -> str:
    esc = html.escape
    out = [f"<h2>{esc(d.headline)}</h2>"]
    if not d.items:
        out.append("<p>Nothing new today.</p>")
    else:
        out.append("<ol>")
        for s in d.items:
            p = s.posting
            out.append(
                f"<li><a href=\"{esc(p.url, quote=True)}\"><b>{esc(p.title)}</b></a><br>"
                f"{esc(_meta(s))}<br><small>{esc(_score_line(s))}</small></li>"
            )
        out.append("</ol>")
    out.append("<p><small>Sent by jobs-digest.</small></p>")
    return "\n".join(out)


def chunk(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split a message on blank lines so no chunk exceeds the limit. Telegram refuses messages over 4096 chars."""
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for block in text.split("\n\n"):
        candidate = block if not current else current + "\n\n" + block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(block) > limit:  # a single oversized block: hard split
            chunks.append(block[:limit])
            block = block[limit:]
        current = block
    if current:
        chunks.append(current)
    return chunks
