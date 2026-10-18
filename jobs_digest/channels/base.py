from __future__ import annotations

from ..digest import Digest


class ChannelError(Exception):
    """Sending failed. The run reports it and leaves the postings unsent so the next run retries."""


class Channel:
    """A place a digest can be delivered to. Subclasses read their secrets from `env` in __init__
    and raise ConfigError there when something is missing, so a misconfigured channel fails before any send."""

    name = "base"

    def __init__(self, options: dict, env: dict):
        self.options = options
        self.env = env

    def send(self, digest: Digest) -> None:  # pragma: no cover - interface
        raise NotImplementedError
