import io

import pytest

import jobs_digest.cli as cli
from jobs_digest.channels.base import Channel, ChannelError
from jobs_digest.config import ConfigError, load_config, load_env_file
from jobs_digest.store import Store

from conftest import FIXTURES, TODAY


class RecordingChannel(Channel):
    name = "telegram"
    fail = False
    sent: list = []

    def send(self, digest):
        if self.fail:
            raise ChannelError("telegram: boom")
        RecordingChannel.sent.append([s.posting.title for s in digest.items])


@pytest.fixture
def fake_channels(monkeypatch):
    RecordingChannel.sent = []
    RecordingChannel.fail = False
    monkeypatch.setattr(cli, "build_channels", lambda configured, env: [RecordingChannel({}, env)])
    return RecordingChannel


def test_dry_run_prints_digest_and_never_writes_store(config, tmp_path):
    config.store = str(tmp_path / "digest.sqlite")
    out = io.StringIO()
    assert cli.run(config, dry_run=True, env={}, today=TODAY, out=out) == 0
    text = out.getvalue()
    assert text.startswith("Jobs digest 2026-10-18: 4 new matches (8 postings scanned, 4 matched your profile)")
    assert " 1. Automation Engineer (n8n, Zapier)" in text and " 4. Technical Writer, Developer Docs" in text
    assert "[dry run] nothing sent" in text and "channels: telegram" in text
    with Store(config.store) as store:
        assert store.stats() == {"postings": 0, "sent": 0}


def test_real_run_sends_once_then_nothing(config, tmp_path, fake_channels):
    config.store = str(tmp_path / "digest.sqlite")
    out = io.StringIO()
    assert cli.run(config, dry_run=False, env={}, today=TODAY, out=out) == 0
    assert fake_channels.sent == [["Automation Engineer (n8n, Zapier)", "QA Automation Engineer (Playwright)",
                                   "Senior Python Developer (CRM - AI/LLM)", "Technical Writer, Developer Docs"]]
    assert "telegram: sent 4 new posting(s)" in out.getvalue()

    # same input again: the store remembers, nothing is sent
    assert cli.run(config, dry_run=False, env={}, today=TODAY, out=io.StringIO()) == 0
    assert len(fake_channels.sent) == 1

    # and a dry run after that shows an empty digest
    out = io.StringIO()
    cli.run(config, dry_run=True, env={}, today=TODAY, out=out)
    assert "0 new matches" in out.getvalue() and "Nothing new today." in out.getvalue()


def test_failed_send_is_retried_next_run(config, tmp_path, fake_channels):
    config.store = str(tmp_path / "digest.sqlite")
    fake_channels.fail = True
    assert cli.run(config, dry_run=False, env={}, today=TODAY, out=io.StringIO()) == cli.EXIT_SEND_FAILED
    assert fake_channels.sent == []
    fake_channels.fail = False
    assert cli.run(config, dry_run=False, env={}, today=TODAY, out=io.StringIO()) == 0
    assert len(fake_channels.sent[0]) == 4


def test_max_items_caps_but_only_sent_items_are_marked(config, tmp_path, fake_channels):
    config.store = str(tmp_path / "digest.sqlite")
    config.profile.max_items = 3
    cli.run(config, dry_run=False, env={}, today=TODAY, out=io.StringIO())
    cli.run(config, dry_run=False, env={}, today=TODAY, out=io.StringIO())
    assert [len(batch) for batch in fake_channels.sent] == [3, 1]


def test_main_exit_codes_and_overrides(tmp_path, monkeypatch, capsys):
    store = tmp_path / "s.sqlite"
    rc = cli.main(["-c", str(FIXTURES / "config.yaml"), "--input", str(FIXTURES / "postings.csv"),
                   "--store", str(store), "--dry-run", "--max-items", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 new match (3 postings scanned, 2 matched your profile)" in out
    assert " 1. Automation Engineer (n8n, Zapier)" in out and "Technical Writer" not in out

    assert cli.main(["-c", str(tmp_path / "missing.yaml"), "--dry-run"]) == cli.EXIT_CONFIG
    assert "config file not found" in capsys.readouterr().err

    # a real run without secrets fails before touching the input or the store
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert cli.main(["-c", str(FIXTURES / "config.yaml"), "--store", str(store), "--env-file", "none"]) == cli.EXIT_CONFIG
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def test_env_file_does_not_override_existing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nexport A=1\nB='two words'\nC=\"3\"\nbad line\n", encoding="utf-8")
    env = {"A": "keep"}
    assert load_env_file(env_file, env) == 2
    assert env == {"A": "keep", "B": "two words", "C": "3"}
    assert load_env_file(tmp_path / "missing", env) == 0


def test_config_validation(tmp_path):
    def cfg(text):
        p = tmp_path / "c.yaml"
        p.write_text(text, encoding="utf-8")
        return p

    with pytest.raises(ConfigError, match="keywords is empty"):
        load_config(cfg("input: {path: x.json}\nprofile: {}\n"))
    with pytest.raises(ConfigError, match="weight for 'python'"):
        load_config(cfg("input: {path: x.json}\nprofile: {keywords: {python: lots}}\n"))
    with pytest.raises(ConfigError, match="input needs one of"):
        load_config(cfg("profile: {keywords: [python]}\n"))
    c = load_config(cfg("input: {url: https://x/y.json}\nprofile: {keywords: [Python, AI], max_age_days: 0}\n"))
    assert c.profile.keywords == {"python": 1.0, "ai": 1.0} and c.profile.max_age_days is None
    assert c.store == "digest.sqlite" and c.enabled_channels() == []
