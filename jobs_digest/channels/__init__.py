"""Channel registry. To add a channel: write a Channel subclass and register it here."""
from __future__ import annotations

from ..config import ConfigError
from .base import Channel, ChannelError
from .email import EmailChannel
from .telegram import TelegramChannel

CHANNELS: dict[str, type[Channel]] = {
    TelegramChannel.name: TelegramChannel,
    EmailChannel.name: EmailChannel,
}


def build_channels(configured: dict[str, dict], env: dict) -> list[Channel]:
    """Instantiate every enabled channel. Raises ConfigError for unknown names or missing secrets."""
    built: list[Channel] = []
    for name, options in configured.items():
        if not options.get("enabled"):
            continue
        cls = CHANNELS.get(name)
        if cls is None:
            raise ConfigError(f"unknown channel '{name}'; available: {', '.join(sorted(CHANNELS))}")
        built.append(cls(options, env))
    return built


__all__ = ["CHANNELS", "Channel", "ChannelError", "build_channels"]
