from jobs_digest.digest import build_digest, chunk, format_email_html, format_telegram, format_text
from jobs_digest.scoring import Scored, rank

from conftest import make_posting


def test_text_format_on_fixture(postings, config, today):
    kept, _ = rank(postings, config.profile, today)
    text = format_text(build_digest(kept[:2], scanned=len(postings), matched=len(kept), today=today))
    assert text.splitlines()[0] == "Jobs digest 2026-10-18: 2 new matches (8 postings scanned, 4 matched your profile)"
    assert " 1. Automation Engineer (n8n, Zapier)" in text
    assert "    Flowline · remoteok · 2026-10-16 · Worldwide · $60,000 - $80,000" in text
    assert "    score 19: python +3, automation (title) +6, n8n (title) +6, zapier (title) +4" in text
    assert "    https://remoteOK.com/remote-jobs/remote-automation-engineer-flowline-1137600?ref=feed" in text
    assert " 2. QA Automation Engineer (Playwright)" in text


def test_empty_digest_says_so(today):
    d = build_digest([], scanned=10, matched=0, today=today)
    assert "1 new match " not in d.headline and "0 new matches" in d.headline
    assert "Nothing new today." in format_text(d)
    assert "Nothing new today." in format_telegram(d)
    assert "Nothing new today." in format_email_html(d)


def test_singular_headline(today):
    d = build_digest([Scored(make_posting(), 5)], scanned=1, matched=1, today=today)
    assert d.headline.startswith("Jobs digest 2026-10-18: 1 new match (")


def test_telegram_and_email_html_escape(today):
    p = make_posting(title="R&D <Lead>", company="A&B", url="https://x.io/j?a=1&b=2")
    d = build_digest([Scored(p, 5, ["python (title) +6"])], scanned=1, matched=1, today=today)
    tg = format_telegram(d)
    assert '<a href="https://x.io/j?a=1&amp;b=2">R&amp;D &lt;Lead&gt;</a>' in tg
    assert "<i>score 5: python (title) +6</i>" in tg
    assert "<br>" not in tg  # Telegram's HTML subset has no <br>
    mail = format_email_html(d)
    assert "<ol>" in mail and "R&amp;D &lt;Lead&gt;" in mail and "A&amp;B" in mail


def test_chunk_splits_on_blank_lines_under_limit():
    blocks = [f"item {i}\n" + "x" * 50 for i in range(40)]
    text = "\n\n".join(blocks)
    parts = chunk(text, limit=300)
    assert len(parts) > 1
    assert all(len(p) <= 300 for p in parts)
    assert "\n\n".join(parts) == text  # nothing lost
    assert chunk("short") == ["short"]
    assert chunk("y" * 700, limit=300) == ["y" * 300, "y" * 300, "y" * 100]
