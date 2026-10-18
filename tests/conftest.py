from datetime import date
from pathlib import Path

import pytest

from jobs_digest.config import load_config
from jobs_digest.models import Posting
from jobs_digest.sources import read_file

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 18)


@pytest.fixture
def today() -> date:
    return TODAY


@pytest.fixture
def config():
    cfg = load_config(FIXTURES / "config.yaml")
    cfg.input.path = str(FIXTURES / "postings.json")
    return cfg


@pytest.fixture
def postings() -> list[Posting]:
    return read_file(FIXTURES / "postings.json")


def make_posting(**kw) -> Posting:
    base = dict(source="test", title="Automation Engineer", company="Acme", url="https://x.io/j/1",
                posted_at="2026-10-16")
    base.update(kw)
    return Posting(**base)
