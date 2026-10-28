from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar.collect import FeedError, collect_all, fetch_feed
from radar.models import Source

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def fake_get(routes: dict):
    def get(url, **kwargs):
        value = routes[url]
        if isinstance(value, Exception):
            raise value
        return value

    return get


RSS = Source("Sample", "https://feeds.example/rss", 1)
ATOM = Source("Releases", "https://feeds.example/atom", 1)


def rss_response():
    return FakeResponse((FIXTURES / "sample.rss").read_bytes())


def test_fetch_feed_parses_rss_items():
    items = fetch_feed(RSS, get=fake_get({RSS.url: rss_response()}))

    first = items[0]
    assert first.title == "Voice agent launch"
    assert first.url == "https://example.com/a?utm_source=x"
    assert first.text == "Big news about agents."
    assert first.published == datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
    assert first.source == "Sample"
    assert first.tier == 1


def test_fetch_feed_parses_atom_items():
    response = FakeResponse((FIXTURES / "sample.atom").read_bytes())

    items = fetch_feed(ATOM, get=fake_get({ATOM.url: response}))

    assert [i.title for i in items] == ["Releases v1.2.0"]
    assert items[0].url == "https://github.com/example/repo/releases/tag/v1.2.0"
    assert items[0].published == datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)


def test_fetch_feed_keeps_descriptive_titles_unprefixed():
    items = fetch_feed(RSS, get=fake_get({RSS.url: rss_response()}))

    assert items[0].title == "Voice agent launch"


def test_fetch_feed_skips_entries_without_link():
    items = fetch_feed(RSS, get=fake_get({RSS.url: rss_response()}))

    assert "No link here" not in [i.title for i in items]


def test_fetch_feed_reads_publisher_url_from_source_tag():
    items = fetch_feed(RSS, get=fake_get({RSS.url: rss_response()}))

    press = next(i for i in items if i.title == "Press story")
    assert press.publisher_url == "https://techcrunch.com"


def test_fetch_feed_strips_html_and_truncates():
    body = "<p>" + "word " * 1000 + "</p>"
    xml = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>Long</title><link>https://example.com/long</link>
    <description><![CDATA[{body}]]></description></item></channel></rss>"""

    items = fetch_feed(RSS, get=fake_get({RSS.url: FakeResponse(xml.encode())}))

    assert "<p>" not in items[0].text
    assert len(items[0].text) == 2000


def test_fetch_feed_raises_feed_error_on_http_error():
    with pytest.raises(FeedError):
        fetch_feed(RSS, get=fake_get({RSS.url: FakeResponse(b"", status=500)}))


def test_collect_all_survives_one_failing_feed():
    get = fake_get({RSS.url: TimeoutError("slow"), ATOM.url: FakeResponse((FIXTURES / "sample.atom").read_bytes())})

    items = collect_all([RSS, ATOM], get=get)

    assert [i.title for i in items] == ["Releases v1.2.0"]


def test_collect_all_survives_malformed_xml():
    get = fake_get({RSS.url: FakeResponse(b"<<<not xml"), ATOM.url: FakeResponse((FIXTURES / "sample.atom").read_bytes())})

    items = collect_all([RSS, ATOM], get=get)

    assert [i.title for i in items] == ["Releases v1.2.0"]
