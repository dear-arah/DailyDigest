from datetime import datetime, timedelta, timezone

from radar.config import SourcesConfig
from radar.filters import badge, is_fresh, matches_topics, resolve_tier
from radar.models import Item

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
CFG = SourcesConfig(sources=(), trusted_domains={"vendor.example": 1, "techcrunch.com": 3})


def make_item(**overrides):
    fields = dict(
        title="Title",
        url="https://example.com/a",
        text="body",
        published=None,
        source="Sample",
        tier=2,
        discovery=False,
        publisher_url=None,
    )
    fields.update(overrides)
    return Item(**fields)


def test_is_fresh_rejects_old():
    item = make_item(published=NOW - timedelta(hours=72))

    assert not is_fresh(item, NOW, max_age_hours=48)


def test_is_fresh_accepts_recent():
    item = make_item(published=NOW - timedelta(hours=3))

    assert is_fresh(item, NOW, max_age_hours=48)


def test_is_fresh_accepts_undated():
    assert is_fresh(make_item(published=None), NOW, max_age_hours=48)


def test_matches_topics_word_boundary():
    assert not matches_topics(make_item(text="reagent chemistry notes"), ["agent"])


def test_matches_topics_is_case_insensitive_and_allows_plural():
    item = make_item(title="New Voice AI agents ship", text="")

    assert matches_topics(item, ["voice ai"])
    assert matches_topics(item, ["agent"])


def test_matches_topics_false_when_no_keyword_present():
    assert not matches_topics(make_item(title="Cooking tips", text="soup"), ["voice ai", "agent"])


def test_resolve_tier_keeps_source_tier():
    assert resolve_tier(make_item(tier=2), CFG) == 2


def test_resolve_tier_discovery_trusted_domain_and_subdomain():
    direct = make_item(discovery=True, url="https://vendor.example/post")
    sub = make_item(discovery=True, url="https://blog.vendor.example/post")

    assert resolve_tier(direct, CFG) == 1
    assert resolve_tier(sub, CFG) == 1


def test_resolve_tier_discovery_prefers_publisher_url():
    item = make_item(
        discovery=True,
        url="https://news.google.com/rss/articles/abc",
        publisher_url="https://techcrunch.com",
    )

    assert resolve_tier(item, CFG) == 3


def test_resolve_tier_discovery_unknown_domain_is_none():
    item = make_item(discovery=True, url="https://random-blog.example/post")

    assert resolve_tier(item, CFG) is None


def test_resolve_tier_does_not_match_lookalike_suffix():
    item = make_item(discovery=True, url="https://notvendor.example/post")

    assert resolve_tier(item, CFG) is None


def test_badge_labels():
    assert badge(1) == "Official"
    assert badge(2) == "Known voice"
    assert badge(3) == "Press"
