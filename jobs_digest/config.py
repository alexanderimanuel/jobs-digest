"""Load config.yaml into plain dataclasses. Secrets never live in the YAML; they come from the environment."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

DEFAULT_CONFIG_FILES = ("config.yaml", "config.example.yaml")


class ConfigError(Exception):
    """A problem with config.yaml or a missing environment variable. Reported without a traceback."""


@dataclass
class Profile:
    keywords: dict[str, float] = field(default_factory=dict)
    title_multiplier: float = 2.0
    must_have: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    min_score: float = 1.0
    max_age_days: int | None = 7
    max_items: int = 10


@dataclass
class InputConfig:
    path: str | None = None
    url: str | None = None
    scraper: dict | None = None  # options passed to remote-jobs-scraper's collect()


@dataclass
class Config:
    input: InputConfig
    profile: Profile
    store: str = "digest.sqlite"
    channels: dict[str, dict] = field(default_factory=dict)  # name -> options (enabled, to, subject, ...)
    source_file: str = ""

    def enabled_channels(self) -> list[str]:
        return [name for name, opts in self.channels.items() if opts.get("enabled")]


def find_config(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise ConfigError(f"config file not found: {explicit}")
        return p
    for name in DEFAULT_CONFIG_FILES:
        if Path(name).is_file():
            return Path(name)
    raise ConfigError("no config.yaml found; copy config.example.yaml to config.yaml or pass -c FILE")


def _as_list(value, what: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(v, (str, int, float)) for v in value):
        raise ConfigError(f"{what} must be a list of strings")
    return [str(v) for v in value]


def _profile(raw: dict) -> Profile:
    kws = raw.get("keywords") or {}
    if isinstance(kws, list):  # allow a plain list; every term weighs 1
        kws = {str(k): 1 for k in kws}
    if not isinstance(kws, dict):
        raise ConfigError("profile.keywords must be a mapping of term: weight (or a list of terms)")
    keywords: dict[str, float] = {}
    for term, weight in kws.items():
        try:
            keywords[str(term).strip().lower()] = float(weight)
        except (TypeError, ValueError):
            raise ConfigError(f"profile.keywords: weight for '{term}' must be a number, got {weight!r}") from None
    if not keywords:
        raise ConfigError("profile.keywords is empty; add at least one term")
    try:
        max_age = raw.get("max_age_days", 7)
        return Profile(
            keywords=keywords,
            title_multiplier=float(raw.get("title_multiplier", 2)),
            must_have=[t.lower() for t in _as_list(raw.get("must_have"), "profile.must_have")],
            avoid=[t.lower() for t in _as_list(raw.get("avoid"), "profile.avoid")],
            min_score=float(raw.get("min_score", 1)),
            max_age_days=int(max_age) if max_age not in (None, 0, False) else None,
            max_items=int(raw.get("max_items", 10)),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"profile: {exc}") from None


def _input(raw: dict) -> InputConfig:
    cfg = InputConfig(path=raw.get("path"), url=raw.get("url"), scraper=raw.get("scraper"))
    if cfg.scraper is not None and not isinstance(cfg.scraper, dict):
        raise ConfigError("input.scraper must be a mapping (keywords, sources, since_days, title_only)")
    if not (cfg.path or cfg.url or cfg.scraper is not None):
        raise ConfigError("input needs one of: path (local CSV/JSON), url (http CSV/JSON) or scraper (options)")
    return cfg


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML ({exc})") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")

    known = {"input", "profile", "store", "channels"}
    for key in raw:
        if key not in known:
            log.warning("%s: unknown top-level key '%s' ignored", path, key)

    channels = raw.get("channels") or {}
    if not isinstance(channels, dict) or not all(isinstance(v, dict) for v in channels.values()):
        raise ConfigError("channels must be a mapping of channel name -> options")

    return Config(
        input=_input(raw.get("input") or {}),
        profile=_profile(raw.get("profile") or {}),
        store=str(raw.get("store") or "digest.sqlite"),
        channels={str(k): dict(v) for k, v in channels.items()},
        source_file=str(path),
    )


def load_env_file(path: str | Path = ".env", environ: dict | None = None) -> int:
    """Read KEY=VALUE lines into the environment without overriding variables that are already set.
    Returns how many variables were set. A missing file is not an error."""
    environ = os.environ if environ is None else environ
    p = Path(path)
    if not p.is_file():
        return 0
    n = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and key not in environ:
            environ[key] = value
            n += 1
    return n


def require_env(name: str, environ: dict | None = None) -> str:
    environ = os.environ if environ is None else environ
    value = (environ.get(name) or "").strip()
    if not value:
        raise ConfigError(f"environment variable {name} is not set (see .env.example)")
    return value
