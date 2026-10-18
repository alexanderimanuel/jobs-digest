import pytest

from jobs_digest.config import ConfigError, InputConfig
from jobs_digest.sources import fetch_url, load_postings, read_file, run_scraper

from conftest import FIXTURES


def test_read_json_and_csv_give_the_same_shape():
    js = {p.url: p for p in read_file(FIXTURES / "postings.json")}
    cs = read_file(FIXTURES / "postings.csv")
    assert len(js) == 8 and len(cs) == 3
    flow = cs[0]
    assert flow.tags == ["automation", "n8n", "python"]
    assert flow.salary == "$60,000 - $80,000"
    assert js[flow.url].tags == flow.tags
    assert js[flow.url].key == flow.key


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        read_file(tmp_path / "nope.json")


class FakeResponse:
    def __init__(self, text, status=200, content_type="application/json"):
        self.text, self.status_code, self.headers = text, status, {"Content-Type": content_type}


class FakeSession:
    def __init__(self, response):
        self.response, self.calls = response, []

    def get(self, url, **kw):
        self.calls.append(url)
        return self.response


def test_fetch_url_uses_session_and_content_type():
    session = FakeSession(FakeResponse((FIXTURES / "postings.json").read_text(encoding="utf-8")))
    postings = fetch_url("https://example.com/latest.json", session)
    assert len(postings) == 8 and session.calls == ["https://example.com/latest.json"]

    csv_text = (FIXTURES / "postings.csv").read_text(encoding="utf-8")
    session = FakeSession(FakeResponse(csv_text, content_type="text/plain"))
    assert len(fetch_url("https://example.com/latest.csv", session)) == 3

    with pytest.raises(ConfigError, match="HTTP 404"):
        fetch_url("https://example.com/x.json", FakeSession(FakeResponse("", status=404)))


def test_load_postings_dispatches(monkeypatch):
    monkeypatch.setattr("jobs_digest.sources.run_scraper", lambda opts: ["scraper", opts])
    assert load_postings(InputConfig(scraper={"keywords": ["ai"]})) == ["scraper", {"keywords": ["ai"]}]
    assert len(load_postings(InputConfig(path=str(FIXTURES / "postings.csv")))) == 3


def test_run_scraper_calls_collect_with_options(monkeypatch):
    import remote_jobs.cli as scraper_cli
    from remote_jobs.models import Job

    captured = {}

    def fake_collect(sources, keywords, since_days, limit, fetchers=None, title_only=False):
        captured.update(sources=sources, keywords=keywords, since_days=since_days, title_only=title_only)
        return [Job(source="remoteok", title="AI Engineer", company="Acme", url="https://x.io/1", tags=["ai"])]

    monkeypatch.setattr(scraper_cli, "collect", fake_collect)
    out = run_scraper({"keywords": ["ai"], "sources": ["remoteok"], "since_days": 14, "title_only": True})
    assert captured == dict(sources=["remoteok"], keywords=["ai"], since_days=14, title_only=True)
    assert out[0].title == "AI Engineer" and out[0].tags == ["ai"]

    with pytest.raises(ConfigError, match="unknown source"):
        run_scraper({"sources": ["monster"]})
