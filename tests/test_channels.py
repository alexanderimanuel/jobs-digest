import smtplib

import pytest

from jobs_digest.channels import build_channels
from jobs_digest.channels.base import ChannelError
from jobs_digest.channels.email import EmailChannel
from jobs_digest.channels.telegram import TelegramChannel
from jobs_digest.config import ConfigError
from jobs_digest.digest import build_digest
from jobs_digest.scoring import Scored

from conftest import TODAY, make_posting

ENV = {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "42",
       "SMTP_HOST": "smtp.example.com", "SMTP_PORT": "2525", "SMTP_USER": "me@example.com", "SMTP_PASSWORD": "pw"}


def digest(n=1):
    items = [Scored(make_posting(url=f"https://x.io/j/{i}", title=f"Job {i}"), 5, ["python (title) +6"]) for i in range(n)]
    return build_digest(items, scanned=n, matched=n, today=TODAY)


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body if body is not None else {"ok": True}
        self.headers = {"Content-Type": "application/json"}
        self.text = str(self._body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return self.responses.pop(0)


def test_build_channels_only_enabled_and_validates_secrets():
    chans = build_channels({"telegram": {"enabled": True}, "email": {"enabled": False, "to": "x@y.z"}}, ENV)
    assert [c.name for c in chans] == ["telegram"]
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        build_channels({"telegram": {"enabled": True}}, {})
    with pytest.raises(ConfigError, match="unknown channel 'slack'"):
        build_channels({"slack": {"enabled": True}}, ENV)


def test_telegram_posts_html_and_splits_long_digests():
    session = FakeSession([FakeResponse(), FakeResponse()])
    chan = TelegramChannel({}, ENV, session=session)
    chan.send(digest(60))  # 60 items is well over 4096 characters
    assert len(session.calls) == 2
    url, payload = session.calls[0]
    assert url == "https://api.telegram.org/bot123:abc/sendMessage"
    assert payload["chat_id"] == "42" and payload["parse_mode"] == "HTML"
    assert payload["text"].startswith("<b>Jobs digest 2026-10-18: 60 new matches")
    assert all(len(c[1]["text"]) <= 4096 for c in session.calls)


def test_telegram_error_becomes_channel_error():
    session = FakeSession([FakeResponse(400, {"ok": False, "description": "Bad Request: chat not found"})])
    with pytest.raises(ChannelError, match="chat not found"):
        TelegramChannel({"chat_id": "99"}, ENV, session=session).send(digest())


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.actions = host, port, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.actions.append("starttls")

    def login(self, user, password):
        self.actions.append(("login", user, password))

    def send_message(self, msg):
        self.actions.append(("send", msg))


def test_email_builds_multipart_message_and_logs_in():
    FakeSMTP.instances.clear()
    chan = EmailChannel({"to": ["a@example.com", "b@example.com"], "subject": "{title} {date}: {count} new"}, ENV,
                        smtp_factory=FakeSMTP)
    chan.send(digest(2))
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.example.com", 2525)
    assert smtp.actions[0] == "starttls" and smtp.actions[1] == ("login", "me@example.com", "pw")
    msg = smtp.actions[2][1]
    assert msg["Subject"] == "Jobs digest 2026-10-18: 2 new"
    assert msg["From"] == "me@example.com" and msg["To"] == "a@example.com, b@example.com"
    parts = {p.get_content_type(): p.get_content() for p in msg.iter_parts()}
    assert "1. Job 0" in parts["text/plain"] and "<ol>" in parts["text/html"]


def test_email_requires_recipient_and_wraps_smtp_errors():
    with pytest.raises(ConfigError, match="channels.email.to"):
        EmailChannel({}, ENV, smtp_factory=FakeSMTP)

    class Broken(FakeSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    with pytest.raises(ChannelError, match="bad credentials"):
        EmailChannel({"to": "a@example.com"}, ENV, smtp_factory=Broken).send(digest())
