from datetime import datetime, timedelta, timezone

from radar.dedupe import SeenStore, normalize_url, title_key
from radar.models import Analysis, Item

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def make_item(title="Voice agent launch", url="https://example.com/a", tier=1):
    return Item(title=title, url=url, text="body", published=None, source="Sample", tier=tier)


def make_analysis(score=8):
    return Analysis(summary="s", score=score, tag="threat", product="Conversational AI Engine", angle="a")


def test_normalize_url_strips_tracking_and_slash():
    url = "HTTPS://WWW.Example.com/a/?utm_source=x&b=1&fbclid=z#frag"

    assert normalize_url(url) == "https://example.com/a?b=1"


def test_title_key_keeps_only_lowercase_alphanumerics():
    assert title_key("Voice Agent Launch!") == "voiceagentlaunch"


def test_seen_matches_same_story_with_utm(tmp_path):
    store = SeenStore(tmp_path / "s.json")
    store.record(make_item(url="https://example.com/a"), None, posted=True, now=NOW)

    assert store.seen(make_item(url="https://example.com/a/?utm_campaign=x"))


def test_seen_matches_same_title_different_url_casing(tmp_path):
    store = SeenStore(tmp_path / "s.json")
    store.record(make_item(title="Voice Agent Launch!", url="https://a.example/x"), None, posted=True, now=NOW)

    assert store.seen(make_item(title="voice agent launch", url="https://b.example/y"))


def test_unseen_item_is_not_seen(tmp_path):
    store = SeenStore(tmp_path / "s.json")

    assert not store.seen(make_item())
    assert store.is_empty()


def test_retry_record_is_not_seen(tmp_path):
    store = SeenStore(tmp_path / "s.json")
    store.record(make_item(), make_analysis(), posted=False, now=NOW, retry=True)

    assert not store.seen(make_item())


def test_unposted_non_retry_record_is_seen(tmp_path):
    store = SeenStore(tmp_path / "s.json")
    store.record(make_item(), make_analysis(2), posted=False, now=NOW)

    assert store.seen(make_item())


def test_prune_drops_old_records(tmp_path):
    store = SeenStore(tmp_path / "s.json")
    store.record(make_item(url="https://example.com/old", title="Old"), None, posted=True, now=NOW - timedelta(days=31))
    store.record(make_item(url="https://example.com/new", title="New"), None, posted=True, now=NOW - timedelta(days=1))

    store.prune(NOW, days=30)

    assert not store.seen(make_item(url="https://example.com/old", title="Old"))
    assert store.seen(make_item(url="https://example.com/new", title="New"))


def test_corrupt_state_file_loads_empty(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json")

    assert SeenStore(path).is_empty()


def test_missing_state_file_loads_empty(tmp_path):
    assert SeenStore(tmp_path / "nope" / "s.json").is_empty()


def test_recent_posted_filters_by_window_and_posted_flag(tmp_path):
    store = SeenStore(tmp_path / "s.json")
    store.record(make_item(url="https://e.com/1", title="Recent"), make_analysis(9), posted=True, now=NOW - timedelta(hours=2))
    store.record(make_item(url="https://e.com/2", title="Stale"), make_analysis(9), posted=True, now=NOW - timedelta(hours=30))
    store.record(make_item(url="https://e.com/3", title="Skipped"), make_analysis(1), posted=False, now=NOW - timedelta(hours=1))

    recent = store.recent_posted(NOW, hours=24)

    assert [r["title"] for r in recent] == ["Recent"]
    assert recent[0]["score"] == 9
    assert recent[0]["angle"] == "a"
    assert recent[0]["url"] == "https://e.com/1"


def test_save_and_reload_roundtrip(tmp_path):
    path = tmp_path / "state" / "s.json"
    store = SeenStore(path)
    store.record(make_item(), make_analysis(), posted=True, now=NOW)
    store.save()

    reloaded = SeenStore(path)

    assert reloaded.seen(make_item())
    assert len(reloaded.recent_posted(NOW)) == 1
