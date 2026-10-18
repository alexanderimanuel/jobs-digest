"""Where postings come from: a local CSV/JSON file, an http(s) URL to one, or remote-jobs-scraper run in-process."""
from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

import requests

from . import __version__
from .config import ConfigError, InputConfig
from .models import Posting

log = logging.getLogger(__name__)

USER_AGENT = f"jobs-digest/{__version__} (+https://github.com/alexanderimanuel/jobs-digest)"
TIMEOUT = 30


def parse_text(text: str, fmt: str) -> list[Posting]:
    """Turn the text of a remote-jobs-scraper CSV or JSON file into postings."""
    if fmt == "json":
        rows = json.loads(text)
        if not isinstance(rows, list):
            raise ConfigError("JSON input must be a list of postings")
    elif fmt == "csv":
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        raise ConfigError(f"unknown input format '{fmt}' (use .csv or .json)")
    postings = [Posting.from_row(r) for r in rows if isinstance(r, dict)]
    return [p for p in postings if p.url and p.title]


def guess_format(name: str) -> str:
    lowered = name.lower().split("?")[0]
    return "json" if lowered.endswith(".json") else "csv"


def read_file(path: str | Path) -> list[Posting]:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"input file not found: {path}")
    return parse_text(p.read_text(encoding="utf-8"), guess_format(p.name))


def fetch_url(url: str, session: requests.Session | None = None) -> list[Posting]:
    session = session or make_session()
    resp = session.get(url, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise ConfigError(f"input url returned HTTP {resp.status_code}: {url}")
    fmt = "json" if "json" in (resp.headers.get("Content-Type") or "") else guess_format(url)
    return parse_text(resp.text, fmt)


def run_scraper(options: dict) -> list[Posting]:
    """Call remote-jobs-scraper as a library. Installed from GitHub as a dependency of this package."""
    try:
        from remote_jobs.cli import collect
        from remote_jobs.sources import SOURCES
    except ImportError:
        raise ConfigError(
            "input.scraper needs the remote-jobs-scraper package: "
            "pip install git+https://github.com/alexanderimanuel/remote-jobs-scraper"
        ) from None
    keywords = [str(k) for k in (options.get("keywords") or [])]
    sources = [str(s) for s in (options.get("sources") or sorted(SOURCES))]
    unknown = [s for s in sources if s not in SOURCES]
    if unknown:
        raise ConfigError(f"input.scraper.sources: unknown source(s) {', '.join(unknown)}; choose from {', '.join(sorted(SOURCES))}")
    since = options.get("since_days")
    jobs = collect(sources, keywords, int(since) if since else None, None, title_only=bool(options.get("title_only")))
    log.info("scraper: %d postings from %s", len(jobs), ", ".join(sources))
    return [Posting.from_row(j.to_row() | {"tags": j.tags}) for j in jobs]


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    return s


def load_postings(cfg: InputConfig, session: requests.Session | None = None) -> list[Posting]:
    if cfg.path:
        log.info("input: file %s", cfg.path)
        return read_file(cfg.path)
    if cfg.url:
        log.info("input: url %s", cfg.url)
        return fetch_url(cfg.url, session)
    log.info("input: running remote-jobs-scraper")
    return run_scraper(cfg.scraper or {})
