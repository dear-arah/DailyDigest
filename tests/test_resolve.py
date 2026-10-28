import json

import requests

from radar.resolve import resolve_url

GNEWS = "https://news.google.com/rss/articles/CBMiAbc123?oc=5"
PAGE = '<c-wiz><div data-n-a-sg="SIG123" data-n-a-ts="1700000000"></div></c-wiz>'


def batch_response(url):
    inner = json.dumps(["garturlres", url, 1])
    outer = json.dumps([["wrb.fr", "Fbv4je", inner, None, None, None, "generic"], ["di", 12]])
    return ")]}'\n\n" + outer


class FakeResponse:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status


class Net:
    def __init__(self, page=PAGE, answer=None, status=200, error=None):
        self.page = page
        self.answer = answer
        self.status = status
        self.error = error
        self.gets = []
        self.posts = []

    def get(self, url, **kwargs):
        self.gets.append(url)
        if self.error:
            raise self.error
        return FakeResponse(self.page, self.status)

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if self.error:
            raise self.error
        return FakeResponse(self.answer or "", self.status)


def test_other_hosts_are_returned_unchanged_without_network():
    net = Net()

    assert resolve_url("https://example.com/post", get=net.get, post=net.post) == "https://example.com/post"
    assert net.gets == [] and net.posts == []


def test_google_news_link_is_resolved_to_the_publisher():
    net = Net(answer=batch_response("https://www.cartesia.ai/mcp"))

    assert resolve_url(GNEWS, get=net.get, post=net.post) == "https://www.cartesia.ai/mcp"
    assert net.gets == ["https://news.google.com/rss/articles/CBMiAbc123"]
    assert "SIG123" in net.posts[0][1]["data"] and "1700000000" in net.posts[0][1]["data"]


def test_falls_back_to_original_when_page_has_no_signature():
    net = Net(page="<html>consent wall</html>")

    assert resolve_url(GNEWS, get=net.get, post=net.post) == GNEWS
    assert net.posts == []


def test_falls_back_to_original_on_network_error():
    net = Net(error=requests.ConnectionError("down"))

    assert resolve_url(GNEWS, get=net.get, post=net.post) == GNEWS


def test_falls_back_to_original_on_http_error():
    net = Net(status=429, answer=batch_response("https://x.example/a"))

    assert resolve_url(GNEWS, get=net.get, post=net.post) == GNEWS


def test_falls_back_to_original_on_unparseable_answer():
    net = Net(answer="nonsense")

    assert resolve_url(GNEWS, get=net.get, post=net.post) == GNEWS


def test_does_not_accept_a_google_url_as_the_answer():
    net = Net(answer=batch_response("https://news.google.com/other"))

    assert resolve_url(GNEWS, get=net.get, post=net.post) == GNEWS
