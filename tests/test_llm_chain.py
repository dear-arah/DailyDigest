import pytest

from radar.llm.chain import FallbackChain, build_chain
from radar.llm.providers import (
    AllProvidersFailed,
    GeminiProvider,
    OpenAICompatProvider,
    ProviderError,
)
from radar.models import ProviderSpec


class FakeProvider:
    def __init__(self, name, result=None, error=None):
        self.name = name
        self.result = result
        self.error = error
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class RecordingPost:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_chain_falls_through_to_second_on_error():
    first = FakeProvider("a", error=ProviderError("boom"))
    second = FakeProvider("b", result="ok")

    assert FallbackChain([first, second]).complete("sys", "user") == "ok"
    assert first.calls == 1 and second.calls == 1


def test_chain_stops_at_first_success():
    first = FakeProvider("a", result="first")
    second = FakeProvider("b", result="second")

    assert FallbackChain([first, second]).complete("s", "u") == "first"
    assert second.calls == 0


def test_chain_tries_next_provider_when_parse_fails():
    first = FakeProvider("a", result="junk")
    second = FakeProvider("b", result="7")

    assert FallbackChain([first, second]).complete("s", "u", parse=int) == 7
    assert first.calls == 1 and second.calls == 1


def test_chain_raises_when_every_output_fails_parse():
    chain = FallbackChain([FakeProvider("a", result="junk"), FakeProvider("b", result="more junk")])

    with pytest.raises(AllProvidersFailed):
        chain.complete("s", "u", parse=int)


def test_chain_raises_when_all_fail():
    chain = FallbackChain([FakeProvider("a", error=ProviderError("x")), FakeProvider("b", error=ProviderError("y"))])

    with pytest.raises(AllProvidersFailed):
        chain.complete("s", "u")


def test_empty_chain_raises():
    with pytest.raises(AllProvidersFailed):
        FallbackChain([]).complete("s", "u")


def test_build_chain_skips_provider_without_key():
    specs = [ProviderSpec("github", "m1"), ProviderSpec("gemini", "m2")]

    chain = build_chain(specs, {"GEMINI_API_KEY": "k"})

    assert [p.name for p in chain.providers] == ["gemini"]


def test_build_chain_keeps_spec_order():
    specs = [ProviderSpec("gemini", "m2"), ProviderSpec("groq", "m3"), ProviderSpec("github", "m1")]
    env = {"GEMINI_API_KEY": "a", "GROQ_API_KEY": "b", "GITHUB_TOKEN": "c"}

    chain = build_chain(specs, env)

    assert [p.name for p in chain.providers] == ["gemini", "groq", "github"]


def test_build_chain_rejects_unknown_provider():
    with pytest.raises(ValueError):
        build_chain([ProviderSpec("nope", "m")], {})


def test_openai_compat_sends_bearer_and_parses_choice():
    post = RecordingPost(FakeResponse({"choices": [{"message": {"content": "hello"}}]}))
    provider = OpenAICompatProvider("groq", "https://api.example/v1", "model-x", "secret", post=post)

    assert provider.complete("be brief", "hi") == "hello"

    url, kwargs = post.calls[0]
    assert url == "https://api.example/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert kwargs["json"]["model"] == "model-x"
    assert kwargs["json"]["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
    ]


def test_gemini_parses_candidate_text():
    payload = {"candidates": [{"content": {"parts": [{"text": "answer"}]}}]}
    post = RecordingPost(FakeResponse(payload))
    provider = GeminiProvider("gemini-test", "secret", post=post)

    assert provider.complete("sys", "user") == "answer"

    url, kwargs = post.calls[0]
    assert url.endswith("/models/gemini-test:generateContent")
    assert kwargs["headers"]["x-goog-api-key"] == "secret"
    assert kwargs["json"]["systemInstruction"]["parts"][0]["text"] == "sys"


def test_http_429_becomes_provider_error():
    provider = OpenAICompatProvider("groq", "https://api.example/v1", "m", "k", post=RecordingPost(FakeResponse({}, status=429)))

    with pytest.raises(ProviderError):
        provider.complete("s", "u")


def test_malformed_body_becomes_provider_error():
    provider = GeminiProvider("m", "k", post=RecordingPost(FakeResponse({"unexpected": True})))

    with pytest.raises(ProviderError):
        provider.complete("s", "u")


def test_network_exception_becomes_provider_error():
    def failing_post(url, **kwargs):
        raise TimeoutError("slow")

    provider = OpenAICompatProvider("groq", "https://api.example/v1", "m", "k", post=failing_post)

    with pytest.raises(ProviderError):
        provider.complete("s", "u")
