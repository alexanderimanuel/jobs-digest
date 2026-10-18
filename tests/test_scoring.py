from datetime import date

from jobs_digest.config import Profile
from jobs_digest.scoring import contains, rank, score

from conftest import make_posting


def profile(**kw) -> Profile:
    base = dict(keywords={"python": 3, "automation": 3, "api": 1}, title_multiplier=2, min_score=1, max_age_days=7)
    base.update(kw)
    return Profile(**base)


def test_terms_match_word_prefix_not_substring():
    assert contains("ai-powered search", "ai")
    assert not contains("account executive retail", "ai")
    assert contains("senior technical  writer", "technical writer")
    assert not contains("technical support writer", "technical writer")
    assert contains("build apis fast", "api")
    assert contains("python/llm stack", "llm")


def test_title_hits_count_double_and_each_term_once():
    p = make_posting(title="Python Automation Engineer", description="python python python, build APIs")
    s = score(p, profile(), today=date(2026, 10, 18))
    assert s.kept
    assert s.score == 3 * 2 + 3 * 2 + 1
    assert s.reasons == ["python (title) +6", "automation (title) +6", "api +1"]


def test_tags_count_once_like_the_description():
    p = make_posting(title="Engineer", tags=["python"])
    assert score(p, profile(), today=date(2026, 10, 18)).reasons == ["python +3"]


def test_avoid_term_drops_posting_wherever_it_appears():
    p = make_posting(title="Python Engineer", location="USA Only")
    s = score(p, profile(avoid=["usa only"]), today=date(2026, 10, 18))
    assert not s.kept and s.rejected == "avoid term: usa only"
    p = make_posting(title="Python Engineer", description="weekly on-call rotation")
    assert score(p, profile(avoid=["on-call"]), today=date(2026, 10, 18)).rejected == "avoid term: on-call"


def test_must_have_requires_at_least_one():
    p = make_posting(title="Python Engineer", description="fully async team")
    assert score(p, profile(must_have=["async", "contract"]), today=date(2026, 10, 18)).kept
    assert not score(p, profile(must_have=["contract"]), today=date(2026, 10, 18)).kept


def test_min_score_and_age():
    old = make_posting(title="Python Engineer", posted_at="2026-10-01")
    assert score(old, profile(), today=date(2026, 10, 18)).rejected.startswith("older than 7 days")
    undated = make_posting(title="Python Engineer", posted_at="")
    assert score(undated, profile(), today=date(2026, 10, 18)).kept  # unknown dates are kept
    weak = make_posting(title="Chef", description="we use an API")
    assert score(weak, profile(min_score=4), today=date(2026, 10, 18)).rejected == "score 1 below minimum 4"
    assert score(old, profile(max_age_days=None), today=date(2026, 10, 18)).kept


def test_rank_on_fixture(postings, config, today):
    kept, dropped = rank(postings, config.profile, today)
    assert [(s.posting.company, s.score) for s in kept] == [
        ("Flowline", 19), ("Testly", 18), ("Emerging Travel Group", 15), ("Docsy", 14),
    ]
    reasons = {s.posting.company: s.rejected for s in dropped}
    assert reasons["Pagerly"] == "avoid term: on-call"
    assert reasons["OldCo"].startswith("older than 7 days")
    assert reasons["Shoply"] == "score 0 below minimum 4"
    assert reasons["Peopleful"] == "score 0 below minimum 4"


def test_rank_ties_newest_first_then_title():
    a = make_posting(title="B job", url="https://x.io/a", posted_at="2026-10-15", tags=["python"])
    b = make_posting(title="A job", url="https://x.io/b", posted_at="2026-10-16", tags=["python"])
    c = make_posting(title="A job", url="https://x.io/c", posted_at="", tags=["python"])
    kept, _ = rank([a, b, c], profile(), today=date(2026, 10, 18))
    assert [s.posting.url for s in kept] == ["https://x.io/b", "https://x.io/a", "https://x.io/c"]
