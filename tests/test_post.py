from datetime import datetime, timezone

from radar.models import Analysis, Item
from radar.post import build_embed, post_embed


def make_item(title="Voice agent launch", published=None):
    return Item(
        title=title,
        url="https://example.com/a",
        text="body",
        published=published,
        source="Vendor Blog",
        tier=1,
    )


def make_analysis(**overrides):
    fields = dict(
        summary="A vendor shipped an SDK.",
        score=8,
        tag="threat",
        product="Conversational AI Engine",
        angle="Competes directly with the engine.",
    )
    fields.update(overrides)
    return Analysis(**fields)


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


class ScriptedPost:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_embed_truncates_title_and_description():
    embed = build_embed(make_item(title="t" * 400), make_analysis(summary="s" * 5000), tier=1)

    assert len(embed["title"]) == 256
    assert len(embed["description"]) == 4096


def test_embed_contains_summary_angle_tag_and_link():
    embed = build_embed(make_item(), make_analysis(), tier=1)

    assert embed["url"] == "https://example.com/a"
    assert "A vendor shipped an SDK." in embed["description"]
    assert "Agora angle" in embed["description"]
    assert "Competes directly with the engine." in embed["description"]
    assert "THREAT" in embed["description"]
    assert "8/10" in embed["description"]


def test_embed_pending_when_no_analysis():
    embed = build_embed(make_item(), None, tier=1)

    assert "Analysis pending" in embed["description"]


def test_embed_footer_has_badge_and_source():
    embed = build_embed(make_item(), make_analysis(), tier=1)

    assert embed["footer"]["text"] == "Official · Vendor Blog"


def test_embed_color_depends_on_tag():
    threat = build_embed(make_item(), make_analysis(tag="threat"), tier=1)
    opportunity = build_embed(make_item(), make_analysis(tag="opportunity"), tier=1)

    assert threat["color"] != opportunity["color"]


def test_embed_timestamp_from_published_date():
    published = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)

    embed = build_embed(make_item(published=published), make_analysis(), tier=1)

    assert embed["timestamp"] == published.isoformat()


def test_post_sends_embeds_payload():
    post = ScriptedPost(FakeResponse(204))
    embed = {"title": "x"}

    assert post_embed("https://hook.example/w", embed, post=post, sleep=lambda s: None) is True

    url, kwargs = post.calls[0]
    assert url == "https://hook.example/w"
    assert kwargs["json"] == {"embeds": [embed]}


def test_post_retries_after_429_then_succeeds():
    post = ScriptedPost(FakeResponse(429, {"retry_after": 1.5}), FakeResponse(204))
    slept = []

    assert post_embed("https://hook.example/w", {}, post=post, sleep=slept.append) is True

    assert slept == [1.5]
    assert len(post.calls) == 2


def test_post_returns_false_when_retry_also_rate_limited():
    post = ScriptedPost(FakeResponse(429, {"retry_after": 1}), FakeResponse(429, {"retry_after": 1}))

    assert post_embed("https://hook.example/w", {}, post=post, sleep=lambda s: None) is False
    assert len(post.calls) == 2


def test_post_returns_false_on_500():
    post = ScriptedPost(FakeResponse(500))

    assert post_embed("https://hook.example/w", {}, post=post, sleep=lambda s: None) is False


def test_post_returns_false_on_network_exception():
    post = ScriptedPost(TimeoutError("slow"))

    assert post_embed("https://hook.example/w", {}, post=post, sleep=lambda s: None) is False
