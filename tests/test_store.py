from jobs_digest.scoring import Scored, rank
from jobs_digest.store import Store

from conftest import make_posting


def scored(**kw) -> Scored:
    return Scored(make_posting(**kw), score=5)


def test_remember_counts_only_new_postings():
    with Store(":memory:") as store:
        a, b = scored(url="https://x.io/j/1"), scored(url="https://x.io/j/2")
        assert store.remember([a, b]) == 2
        assert store.remember([a, scored(url="https://x.io/j/3")]) == 1
        assert store.stats() == {"postings": 3, "sent": 0}


def test_identity_is_the_canonical_url():
    with Store(":memory:") as store:
        a = scored(url="https://RemoteOK.com/remote-jobs/1?ref=feed")
        b = scored(url="https://remoteok.com/remote-jobs/1/")
        assert store.remember([a]) == 1
        assert store.remember([b]) == 0
        store.mark_sent([a], "telegram")
        assert store.unsent([b], "telegram") == []


def test_unsent_is_per_channel_and_keeps_order():
    with Store(":memory:") as store:
        items = [scored(url=f"https://x.io/j/{i}") for i in range(4)]
        store.remember(items)
        store.mark_sent(items[1:3], "telegram")
        assert [s.posting.url for s in store.unsent(items, "telegram")] == ["https://x.io/j/0", "https://x.io/j/3"]
        assert store.unsent(items, "email") == items
        assert store.unsent([], "telegram") == []


def test_second_run_sends_nothing(tmp_path, postings, config, today):
    kept, _ = rank(postings, config.profile, today)
    path = tmp_path / "digest.sqlite"
    with Store(path) as store:
        store.remember(kept)
        fresh = store.unsent(kept, "telegram")
        assert len(fresh) == 4
        store.mark_sent(fresh, "telegram")
    with Store(path) as store:  # a new process, same file
        assert store.unsent(kept, "telegram") == []
        assert store.stats() == {"postings": 4, "sent": 4}
