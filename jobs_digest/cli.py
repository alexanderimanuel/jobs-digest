from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date

from .channels import ChannelError, build_channels
from .config import Config, ConfigError, find_config, load_config, load_env_file
from .digest import build_digest, format_text
from .scoring import Scored, rank
from .sources import load_postings
from .store import Store

log = logging.getLogger("jobs_digest")

EXIT_OK, EXIT_CONFIG, EXIT_SEND_FAILED = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jobs_digest",
        description="Score remote job postings against your YAML profile and send only the new matches "
                    "to Telegram or email.",
    )
    p.add_argument("-c", "--config", metavar="FILE",
                   help="YAML config (default: config.yaml, falling back to config.example.yaml)")
    p.add_argument("--input", metavar="FILE_OR_URL",
                   help="read postings from this CSV/JSON file or URL instead of what the config says")
    p.add_argument("--store", metavar="FILE", help="SQLite store path (overrides config)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the digest instead of sending it; reads the store but never writes it")
    p.add_argument("--max-items", type=int, metavar="N", help="cap the digest at N postings (overrides config)")
    p.add_argument("--env-file", default=".env", metavar="FILE",
                   help="load KEY=VALUE secrets from this file if it exists (default: .env)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="log every dropped posting with the reason, plus per-step counts")
    return p


def apply_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    if args.input:
        if args.input.startswith(("http://", "https://")):
            cfg.input.path, cfg.input.url, cfg.input.scraper = None, args.input, None
        else:
            cfg.input.path, cfg.input.url, cfg.input.scraper = args.input, None, None
    if args.store:
        cfg.store = args.store
    if args.max_items is not None:
        cfg.profile.max_items = args.max_items
    return cfg


def run(cfg: Config, dry_run: bool, env: dict | None = None, today: date | None = None, out=None) -> int:
    """The pipeline: load -> score -> filter through the store -> send (or print). Returns an exit code."""
    env = os.environ if env is None else env
    today = today or date.today()
    out = out or sys.stdout

    channels = []
    if not dry_run:
        channels = build_channels(cfg.channels, env)  # fail on missing secrets before doing any work
        if not channels:
            raise ConfigError("no channel is enabled in config; enable one or use --dry-run")

    postings = load_postings(cfg.input)
    kept, dropped = rank(postings, cfg.profile, today)
    log.info("scored %d postings: %d matched, %d dropped", len(postings), len(kept), len(dropped))
    for s in dropped:
        log.debug("dropped: %s (%s) - %s", s.posting.title, s.posting.company, s.rejected)

    with Store(cfg.store) as store:
        if dry_run:
            names = cfg.enabled_channels()
            fresh = _unsent_for_any(store, kept, names) if names else kept
            digest = build_digest(fresh[: cfg.profile.max_items], len(postings), len(kept), today)
            out.write(format_text(digest))
            out.write(f"\n[dry run] nothing sent, store {cfg.store} untouched"
                      f"{'; channels: ' + ', '.join(names) if names else '; no channel enabled'}\n")
            return EXIT_OK

        new_to_store = store.remember(kept)
        log.info("store %s: %d postings new to the store", cfg.store, new_to_store)
        failures = 0
        for channel in channels:
            fresh = store.unsent(kept, channel.name)
            if not fresh:
                log.info("%s: nothing new, not sending", channel.name)
                continue
            digest = build_digest(fresh[: cfg.profile.max_items], len(postings), len(kept), today)
            try:
                channel.send(digest)
            except ChannelError as exc:
                failures += 1
                log.error("%s: send failed, will retry next run (%s)", channel.name, exc)
                continue
            store.mark_sent(digest.items, channel.name)
            print(f"{channel.name}: sent {len(digest.items)} new posting(s)", file=out)
        return EXIT_SEND_FAILED if failures else EXIT_OK


def _unsent_for_any(store: Store, kept: list[Scored], names: list[str]) -> list[Scored]:
    """Items at least one enabled channel has not received yet (what a real run would send)."""
    pending = {s.posting.key for name in names for s in store.unsent(kept, name)}
    return [s for s in kept if s.posting.key in pending]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    if hasattr(sys.stdout, "reconfigure"):  # never crash on a terminal that cannot print "·"
        sys.stdout.reconfigure(errors="replace")
    try:
        load_env_file(args.env_file)
        cfg = apply_overrides(load_config(find_config(args.config)), args)
        log.info("config: %s", cfg.source_file)
        return run(cfg, dry_run=args.dry_run)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
