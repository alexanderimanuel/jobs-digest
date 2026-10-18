"""Telegram Bot API: one sendMessage per 4096-character chunk, HTML formatting."""
from __future__ import annotations

import requests

from ..config import require_env
from ..digest import Digest, chunk, format_telegram
from .base import Channel, ChannelError

API = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT = 30


class TelegramChannel(Channel):
    name = "telegram"

    def __init__(self, options: dict, env: dict, session: requests.Session | None = None):
        super().__init__(options, env)
        self.token = require_env("TELEGRAM_BOT_TOKEN", env)
        self.chat_id = str(options.get("chat_id") or require_env("TELEGRAM_CHAT_ID", env))
        self.session = session or requests.Session()

    def send(self, digest: Digest) -> None:
        for part in chunk(format_telegram(digest)):
            payload = {"chat_id": self.chat_id, "text": part, "parse_mode": "HTML", "disable_web_page_preview": True}
            try:
                resp = self.session.post(API.format(token=self.token), json=payload, timeout=TIMEOUT)
            except requests.RequestException as exc:
                raise ChannelError(f"telegram: {exc}") from None
            body = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {}
            if resp.status_code != 200 or not body.get("ok"):
                raise ChannelError(f"telegram: HTTP {resp.status_code} {body.get('description') or resp.text[:200]}")
