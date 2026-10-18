from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

FIELDS = ["source", "title", "company", "location", "salary", "tags", "posted_at", "url", "description"]


def canonical_url(url: str) -> str:
    """Lower-case host, drop query string and fragment, strip trailing slash. This is the identity of a posting."""
    parts = urlsplit((url or "").strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


@dataclass
class Posting:
    """One job posting in the shape remote-jobs-scraper writes (same nine columns)."""

    source: str
    title: str
    company: str
    url: str
    location: str = ""
    salary: str = ""
    tags: list[str] = field(default_factory=list)
    posted_at: str = ""  # YYYY-MM-DD or "" when the board gave no date
    description: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "Posting":
        tags = row.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        return cls(
            source=str(row.get("source") or ""),
            title=str(row.get("title") or "").strip(),
            company=str(row.get("company") or "").strip(),
            url=str(row.get("url") or "").strip(),
            location=str(row.get("location") or "").strip(),
            salary=str(row.get("salary") or "").strip(),
            tags=[str(t) for t in tags],
            posted_at=str(row.get("posted_at") or "")[:10],
            description=str(row.get("description") or "").strip(),
        )

    @property
    def key(self) -> str:
        return canonical_url(self.url)

    def head_text(self) -> str:
        """Where a keyword hit counts title_multiplier times: the title only. Boards attach long, generic
        tag lists ("dev, python, javascript, ...") so tags are only worth a single hit."""
        return self.title.lower()

    def body_text(self) -> str:
        return " ".join([" ".join(self.tags), self.company, self.location, self.salary, self.description]).lower()

    def all_text(self) -> str:
        return self.head_text() + " " + self.body_text()
