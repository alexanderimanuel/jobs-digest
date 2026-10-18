"""Score postings against a profile: weighted keywords, must-have and avoid terms, age and a minimum score."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

from .config import Profile
from .models import Posting


@lru_cache(maxsize=512)
def term_pattern(term: str) -> re.Pattern:
    """Case-insensitive match at the start of a word, so "ai" hits "AI-powered" but not "retail".
    Spaces in a term match any whitespace, so "technical writer" also hits "Technical  Writer"."""
    words = [re.escape(w) for w in term.lower().split()]
    return re.compile(r"(?<![a-z0-9])" + r"\s+".join(words))


def contains(text: str, term: str) -> bool:
    return bool(term_pattern(term).search(text))


@dataclass
class Scored:
    posting: Posting
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)  # e.g. "python (title) +6"
    rejected: str | None = None  # why the posting was dropped, None if kept

    @property
    def kept(self) -> bool:
        return self.rejected is None


def _fmt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def score(posting: Posting, profile: Profile, today: date | None = None) -> Scored:
    """Apply the profile to one posting. Order: age, avoid terms, must-have terms, keywords, minimum score."""
    out = Scored(posting)
    today = today or date.today()

    if profile.max_age_days and posting.posted_at:
        cutoff = (today - timedelta(days=profile.max_age_days)).isoformat()
        if posting.posted_at < cutoff:
            out.rejected = f"older than {profile.max_age_days} days ({posting.posted_at})"
            return out

    text = posting.all_text()
    for term in profile.avoid:
        if contains(text, term):
            out.rejected = f"avoid term: {term}"
            return out

    if profile.must_have and not any(contains(text, t) for t in profile.must_have):
        out.rejected = "none of the must-have terms: " + ", ".join(profile.must_have)
        return out

    head, body = posting.head_text(), posting.body_text()
    for term, weight in profile.keywords.items():
        if contains(head, term):
            pts = weight * profile.title_multiplier
            out.reasons.append(f"{term} (title) +{_fmt(pts)}")
        elif contains(body, term):
            pts = weight
            out.reasons.append(f"{term} +{_fmt(pts)}")
        else:
            continue
        out.score += pts

    if out.score < profile.min_score:
        out.rejected = f"score {_fmt(out.score)} below minimum {_fmt(profile.min_score)}"
    return out


def rank(postings: list[Posting], profile: Profile, today: date | None = None) -> tuple[list[Scored], list[Scored]]:
    """Score every posting. Returns (kept sorted best first, dropped)."""
    scored = [score(p, profile, today) for p in postings]
    kept = [s for s in scored if s.kept]
    dropped = [s for s in scored if not s.kept]
    # best score first; newest first on ties; title as the final tie-break so output is stable
    kept.sort(key=lambda s: (-s.score, _neg_date(s.posting.posted_at), s.posting.title.lower()))
    return kept, dropped


def _neg_date(iso: str) -> str:
    """Map YYYY-MM-DD to a string that sorts newest first. Unknown dates sort last."""
    if not iso:
        return "~"
    return "".join(chr(ord("9") - (ord(c) - ord("0"))) if c.isdigit() else c for c in iso)
