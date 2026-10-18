"""Email over SMTP with STARTTLS: plain-text body plus an HTML alternative."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from ..config import ConfigError, require_env
from ..digest import Digest, format_email_html, format_text
from .base import Channel, ChannelError

TIMEOUT = 30


class EmailChannel(Channel):
    name = "email"

    def __init__(self, options: dict, env: dict, smtp_factory=smtplib.SMTP):
        super().__init__(options, env)
        self.host = require_env("SMTP_HOST", env)
        self.port = int(env.get("SMTP_PORT") or 587)
        self.user = require_env("SMTP_USER", env)
        self.password = require_env("SMTP_PASSWORD", env)
        to = options.get("to")
        if not to:
            raise ConfigError("channels.email.to is required")
        self.to = [to] if isinstance(to, str) else [str(t) for t in to]
        self.sender = str(options.get("from") or self.user)
        self.subject = str(options.get("subject") or "{title} {date}: {count} new matches")
        self.starttls = bool(options.get("starttls", True))
        self.smtp_factory = smtp_factory

    def build_message(self, digest: Digest) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = self.subject.format(date=digest.date, count=len(digest.items), title=digest.title)
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.to)
        msg.set_content(format_text(digest))
        msg.add_alternative(format_email_html(digest), subtype="html")
        return msg

    def send(self, digest: Digest) -> None:
        msg = self.build_message(digest)
        try:
            with self.smtp_factory(self.host, self.port, timeout=TIMEOUT) as smtp:
                if self.starttls:
                    smtp.starttls()
                smtp.login(self.user, self.password)
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise ChannelError(f"email: {exc}") from None
