import json
from datetime import datetime, timedelta, timezone

import pytest

from radar.collect import collect_all
from radar.huggingface import enrich, fetch_models
from radar.models import Item, Source

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
URL = "https://huggingface.co/api/models?pipeline_tag=text-to-speech&sort=trendingScore&limit=40"
SOURCE = Source("HF: text-to-speech", URL, 4, kind="huggingface", min_likes=10, max_age_days=21)


class FakeResponse:
    def __init__(self, payload=None, text="", status=200):
        self._payload = payload
        self.text = text
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def model(model_id, *, days_old=1, likes=36, tags=None, pipeline="text-to-speech", downloads=0):
    created = NOW - timedelta(days=days_old)
    return {
        "id": model_id,
        "createdAt": created.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "likes": likes,
        "downloads": downloads,
        "pipeline_tag": pipeline,
        "tags": tags if tags is not None else ["onnx", "text-to-speech", "region:us", "license:mit"],
    }


def get_for(payload):
    def get(url, **kwargs):
        return FakeResponse(payload)

    return get


def test_fetch_models_builds_an_item_from_the_listing():
    items = fetch_models(SOURCE, get=get_for([model("empero-ai/PiVo-1.4M")]), now=NOW)

    item = items[0]
    assert item.title == "empero-ai/PiVo-1.4M (text-to-speech model)"
    assert item.url == "https://huggingface.co/empero-ai/PiVo-1.4M"
    assert item.source == "HF: text-to-speech"
    assert item.tier == 4
    assert item.discovery is False
    assert item.published == NOW
    assert "text-to-speech" in item.text
    assert "36 likes" in item.text
    assert "onnx" in item.text
    assert "region:us" not in item.text


def test_fetch_models_drops_low_like_and_old_models():
    payload = [
        model("a/popular", likes=50),
        model("b/unliked", likes=3),
        model("c/old", days_old=60, likes=500),
    ]

    items = fetch_models(SOURCE, get=get_for(payload), now=NOW)

    assert [i.url for i in items] == ["https://huggingface.co/a/popular"]


def test_fetch_models_skips_malformed_entries():
    payload = [{"id": "a/no-date", "likes": 99}, model("b/good")]

    items = fetch_models(SOURCE, get=get_for(payload), now=NOW)

    assert [i.url for i in items] == ["https://huggingface.co/b/good"]


def test_fetch_models_raises_on_http_error():
    def get(url, **kwargs):
        return FakeResponse(status=503)

    with pytest.raises(RuntimeError):
        fetch_models(SOURCE, get=get, now=NOW)


def test_collect_all_dispatches_huggingface_sources():
    items = collect_all([SOURCE], get=get_for([model("empero-ai/PiVo-1.4M", days_old=0)]))

    assert [i.url for i in items] == ["https://huggingface.co/empero-ai/PiVo-1.4M"]


def test_collect_all_skips_a_failing_huggingface_source():
    def get(url, **kwargs):
        raise RuntimeError("boom")

    assert collect_all([SOURCE], get=get) == []


def hf_item(url="https://huggingface.co/empero-ai/PiVo-1.4M", text="Hugging Face model."):
    return Item("PiVo", url, text, NOW, "HF: text-to-speech", 4)


README = "---\nlicense: mit\ntags:\n- tts\n---\n# PiVo-1.4M\n\nA 5.8MB TTS model that runs on CPU."


def test_enrich_appends_the_model_card_without_front_matter():
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return FakeResponse(text=README)

    item = enrich(hf_item(), get=get)

    assert calls == ["https://huggingface.co/empero-ai/PiVo-1.4M/raw/main/README.md"]
    assert item.text.startswith("Hugging Face model.")
    assert "A 5.8MB TTS model that runs on CPU." in item.text
    assert "license: mit" not in item.text


def test_enrich_limits_the_model_card_length():
    long_card = "word " * 5000

    item = enrich(hf_item(), get=lambda url, **kw: FakeResponse(text=long_card))

    assert len(item.text) <= 2000 + len("Hugging Face model.") + 1


def test_enrich_leaves_the_item_alone_when_the_card_cannot_be_read():
    def get(url, **kwargs):
        return FakeResponse(status=404)

    original = hf_item()

    assert enrich(original, get=get) is original


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/post",
        "https://huggingface.co/blog/some-post",
        "https://huggingface.co/spaces/townbox/ava",
        "https://huggingface.co/papers/2603.02641",
        "https://huggingface.co/nvidia",
    ],
)
def test_enrich_only_touches_model_pages(url):
    def get(url, **kwargs):
        raise AssertionError("no request expected")

    original = hf_item(url=url)

    assert enrich(original, get=get) is original


def test_text_names_the_uploader_and_says_the_hub_only_hosts_the_model():
    item = fetch_models(SOURCE, get=get_for([model("FermionResearch/Phonon-2.5")]), now=NOW)[0]

    assert "uploaded to the Hugging Face Hub by FermionResearch" in item.text
    assert "only hosts it" in item.text
