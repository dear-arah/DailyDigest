import json
from datetime import datetime, timedelta, timezone

from radar.analyze import parse_analysis
from radar.config import SourcesConfig
from radar.dedupe import SeenStore
from radar.llm.chain import FallbackChain
from radar.llm.providers import ProviderError
from radar.models import Channel, Item, ProviderSpec, Source
from radar.run import ANALYSIS_PAUSE, run_channel, run_digest

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
CFG = SourcesConfig(
    sources=(Source("S", "https://f.example/rss", 1),),
    trusted_domains={"trusted.example": 1},
)
HOOK = "https://hook.example/w"


def make_channel(**overrides):
    fields = dict(
        name="news",
        webhook_env="HOOK",
        sources_file="s",
        context_file="c",
        keywords=("voice ai",),
        threshold=6,
        max_posts_per_run=8,
        max_age_hours=48,
        providers=(ProviderSpec("gemini", "m"),),
    )
    fields.update(overrides)
    return Channel(**fields)


def make_item(title, published=NOW - timedelta(hours=1), discovery=False, url=None, text="voice ai news", tier=1):
    return Item(
        title=title,
        url=url or f"https://example.com/{title.replace(' ', '-')}",
        text=text,
        published=published,
        source="S",
        tier=tier,
        discovery=discovery,
    )


class ScoreProvider:
    name = "fake"

    def __init__(self, scores=None, default=8, error=None):
        self.scores = scores or {}
        self.default = default
        self.error = error
        self.calls = []

    def complete(self, system, user):
        self.calls.append(user)
        if self.error:
            raise self.error
        score = self.default
        for title, value in self.scores.items():
            if f"Title: {title}\n" in user:
                score = value
        return json.dumps(
            {"summary": "Summary.", "score": score, "tag": "threat", "product": "General", "angle": "Angle."}
        )


class PostRecorder:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.embeds = []

    def __call__(self, webhook_url, embed, **kwargs):
        self.embeds.append(embed)
        return self.results.pop(0) if self.results else True


def seeded_store(tmp_path):
    store = SeenStore(tmp_path / "state.json")
    store.record(make_item("Already known"), None, posted=True, now=NOW - timedelta(days=1))
    return store


def run(tmp_path, items, *, store=None, provider=None, post=None, channel=None, dry_run=False, resolve=lambda url: url, sleep=lambda seconds: None):
    store = store or seeded_store(tmp_path)
    provider = provider or ScoreProvider()
    post = post or PostRecorder()
    report = run_channel(
        channel or make_channel(),
        CFG,
        context="ctx",
        store=store,
        chain=FallbackChain([provider]),
        now=NOW,
        collect=lambda sources: items,
        post=post,
        resolve=resolve,
        sleep=sleep,
        webhook_url=HOOK,
        dry_run=dry_run,
    )
    return report, store, provider, post


def test_first_run_seeds_state_and_posts_nothing(tmp_path):
    store = SeenStore(tmp_path / "state.json")
    items = [make_item("One"), make_item("Two")]

    report, store, provider, post = run(tmp_path, items, store=store)

    assert post.embeds == []
    assert provider.calls == []
    assert report.posted == 0
    assert store.seen(items[0]) and store.seen(items[1])
    assert (tmp_path / "state.json").exists()


def test_second_run_posts_new_relevant_item_once(tmp_path):
    items = [make_item("Already known"), make_item("Fresh news")]
    store = seeded_store(tmp_path)

    report, store, _, post = run(tmp_path, items, store=store)
    report_again, _, _, post_again = run(tmp_path, items, store=store)

    assert [e["title"] for e in post.embeds] == ["Fresh news"]
    assert report.posted == 1
    assert post_again.embeds == []
    assert report_again.posted == 0


def test_below_threshold_not_posted_but_remembered(tmp_path):
    items = [make_item("Minor thing")]

    report, store, provider, post = run(tmp_path, items, provider=ScoreProvider(default=3))

    assert post.embeds == []
    assert store.seen(items[0])
    assert len(provider.calls) == 1


def test_untrusted_discovery_dropped_without_llm_call(tmp_path):
    items = [make_item("Rumor", discovery=True, url="https://random-blog.example/x")]

    report, _, provider, post = run(tmp_path, items)

    assert post.embeds == []
    assert provider.calls == []
    assert report.skipped_untrusted == 1


def test_trusted_discovery_item_is_posted(tmp_path):
    items = [make_item("Vendor news", discovery=True, url="https://blog.trusted.example/x")]

    _, _, _, post = run(tmp_path, items)

    assert [e["title"] for e in post.embeds] == ["Vendor news"]


def test_excluded_patterns_are_dropped_without_llm_call(tmp_path):
    channel = make_channel(exclude=(r"\balternatives?\b", "/vs/"))
    items = [
        make_item("Acme TTS alternative for voice agents | Acme"),
        make_item("Acme versus Beta", url="https://acme.example/vs/beta"),
        make_item("Acme ships new voice ai model"),
    ]

    _, _, provider, post = run(tmp_path, items, channel=channel)

    assert [e["title"] for e in post.embeds] == ["Acme ships new voice ai model"]
    assert len(provider.calls) == 1


def test_posted_link_is_resolved_but_dedupe_uses_the_original(tmp_path):
    original = "https://redirect.example/abc"
    items = [make_item("Fresh news", url=original)]
    store = seeded_store(tmp_path)

    _, store, _, post = run(tmp_path, items, store=store, resolve=lambda url: "https://publisher.example/story")
    again, _, _, post_again = run(tmp_path, items, store=store)

    assert post.embeds[0]["url"] == "https://publisher.example/story"
    posted = {r["title"]: r["url"] for r in store.recent_posted(NOW, hours=24)}
    assert posted["Fresh news"] == "https://publisher.example/story"
    assert store.seen(items[0])
    assert post_again.embeds == []


def test_excluded_pattern_is_checked_against_the_resolved_link(tmp_path):
    channel = make_channel(exclude=("/(product|solutions)/",))
    items = [
        make_item("Voice agents page", url="https://redirect.example/a"),
        make_item("Real release notes", url="https://redirect.example/b"),
    ]
    resolved = {
        "https://redirect.example/a": "https://vendor.example/product/voice-agents",
        "https://redirect.example/b": "https://vendor.example/blog/release-notes",
    }

    _, store, _, post = run(tmp_path, items, channel=channel, resolve=resolved.get)

    assert [e["title"] for e in post.embeds] == ["Real release notes"]
    assert store.seen(items[0])


def test_resolver_is_not_called_for_items_that_are_not_posted(tmp_path):
    calls = []
    items = [make_item("Minor thing")]

    run(tmp_path, items, provider=ScoreProvider(default=3), resolve=lambda url: calls.append(url) or url)

    assert calls == []


def test_stale_and_off_topic_items_are_skipped(tmp_path):
    items = [
        make_item("Old story", published=NOW - timedelta(hours=100)),
        make_item("Cooking tips", text="soup recipes"),
    ]

    _, _, provider, post = run(tmp_path, items)

    assert post.embeds == []
    assert provider.calls == []


def test_same_story_from_two_feeds_posted_once(tmp_path):
    items = [
        make_item("Fresh news", url="https://a.example/story?utm_source=x"),
        make_item("Fresh news", url="https://a.example/story"),
        make_item("FRESH NEWS!", url="https://b.example/other-url"),
    ]

    report, _, provider, post = run(tmp_path, items)

    assert [e["title"] for e in post.embeds] == ["Fresh news"]
    assert len(provider.calls) == 1


def test_post_failure_leaves_item_retryable(tmp_path):
    items = [make_item("Fresh news")]
    store = seeded_store(tmp_path)

    first_report, store, _, _ = run(tmp_path, items, store=store, post=PostRecorder([False]))
    assert first_report.posted == 0
    assert not store.seen(items[0])

    second_report, _, _, post = run(tmp_path, items, store=store, post=PostRecorder([True]))

    assert second_report.posted == 1
    assert [e["title"] for e in post.embeds] == ["Fresh news"]


def test_failed_posts_are_counted_in_the_report(tmp_path):
    items = [make_item("One"), make_item("Two")]

    report, _, _, _ = run(tmp_path, items, post=PostRecorder([False, True]))

    assert report.failed == 1
    assert report.posted == 1


def test_posts_capped_and_highest_score_first(tmp_path):
    items = [make_item("Low"), make_item("Top"), make_item("Mid")]
    provider = ScoreProvider(scores={"Low": 7, "Top": 9, "Mid": 8})

    report, _, _, post = run(tmp_path, items, provider=provider, channel=make_channel(max_posts_per_run=2))

    assert [e["title"] for e in post.embeds] == ["Top", "Mid"]
    assert report.posted == 2


def test_analysis_calls_are_paced(tmp_path):
    sleeps = []
    items = [make_item(f"Story {n}") for n in range(3)]

    run(tmp_path, items, sleep=sleeps.append)

    assert sleeps == [ANALYSIS_PAUSE, ANALYSIS_PAUSE]


def test_analysis_cap_limits_llm_calls(tmp_path):
    items = [make_item(f"Story {n}") for n in range(10)]

    _, _, provider, _ = run(tmp_path, items, channel=make_channel(max_posts_per_run=2))

    assert len(provider.calls) == 6


def test_dry_run_posts_nothing_and_records_nothing(tmp_path, capsys):
    items = [make_item("Fresh news")]
    store = seeded_store(tmp_path)

    report, store, _, post = run(tmp_path, items, store=store, dry_run=True)

    assert post.embeds == []
    assert "Fresh news" in capsys.readouterr().out
    assert not store.seen(items[0])
    assert report.posted == 1


def test_dry_run_on_empty_store_still_shows_items(tmp_path, capsys):
    store = SeenStore(tmp_path / "state.json")

    run(tmp_path, [make_item("Fresh news")], store=store, dry_run=True)

    assert "Fresh news" in capsys.readouterr().out
    assert not (tmp_path / "state.json").exists()


def test_analysis_failure_posts_pending(tmp_path):
    items = [make_item("Fresh news")]

    report, _, _, post = run(tmp_path, items, provider=ScoreProvider(error=ProviderError("down")))

    assert "Analysis pending" in post.embeds[0]["description"]
    assert report.pending == 1


def test_pending_posts_limited_to_two_official_items(tmp_path):
    items = [make_item(f"Story {n}") for n in range(4)]

    report, store, _, post = run(tmp_path, items, provider=ScoreProvider(error=ProviderError("down")))

    assert len(post.embeds) == 2
    assert report.pending == 2
    assert sum(store.seen(i) for i in items) == 2


def test_pending_not_posted_for_non_official_items_and_retried_later(tmp_path):
    items = [make_item("Press story", tier=3)]

    _, store, _, post = run(tmp_path, items, provider=ScoreProvider(error=ProviderError("down")))

    assert post.embeds == []
    assert not store.seen(items[0])


def test_one_broken_item_does_not_stop_the_run(tmp_path):
    class Flaky(ScoreProvider):
        def complete(self, system, user):
            if "Title: Boom\n" in user:
                raise RuntimeError("unexpected")
            return super().complete(system, user)

    items = [make_item("Boom"), make_item("Fine")]

    _, _, _, post = run(tmp_path, items, provider=Flaky())

    assert [e["title"] for e in post.embeds] == ["Fine"]
    assert (tmp_path / "state.json").exists()


def test_run_digest_posts_recent_records(tmp_path):
    store = seeded_store(tmp_path)
    analysis = parse_analysis(
        json.dumps({"summary": "S.", "score": 9, "tag": "fyi", "product": "General", "angle": "A."})
    )
    store.record(make_item("Fresh news"), analysis, posted=True, now=NOW - timedelta(hours=2))
    post = PostRecorder()

    assert run_digest(store, HOOK, NOW, post=post) == "posted"

    assert "fields" in post.embeds[0]


def test_run_digest_reports_failure_when_discord_rejects_it(tmp_path):
    store = seeded_store(tmp_path)
    analysis = parse_analysis(
        json.dumps({"summary": "S.", "score": 9, "tag": "fyi", "product": "General", "angle": "A."})
    )
    store.record(make_item("Fresh news"), analysis, posted=True, now=NOW - timedelta(hours=2))

    assert run_digest(store, HOOK, NOW, post=PostRecorder([False])) == "failed"


def test_run_digest_returns_false_when_nothing_to_post(tmp_path):
    store = SeenStore(tmp_path / "state.json")
    post = PostRecorder()

    assert run_digest(store, HOOK, NOW, post=post) == "empty"
    assert post.embeds == []
