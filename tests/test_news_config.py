from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar.config import load_channel
from radar.filters import matches_topics
from radar.models import Item

CHANNEL = Path(__file__).resolve().parent.parent / "config" / "channels" / "news.yaml"


def item(title, text=""):
    return Item(
        title=title,
        url="https://example.com/x",
        text=text,
        published=datetime(2026, 10, 28, tzinfo=timezone.utc),
        source="S",
        tier=1,
    )


@pytest.fixture(scope="module")
def keywords():
    return load_channel(CHANNEL).keywords


@pytest.mark.parametrize("word", ["llm", "openai", "anthropic", "gemini", "multimodal", "agentic"])
def test_company_names_and_generic_ai_terms_are_not_keywords(keywords, word):
    assert word not in keywords


@pytest.mark.parametrize("word", ["voice ai", "voice agent", "conversational ai", "text-to-speech", "webrtc"])
def test_core_voice_terms_are_keywords(keywords, word):
    assert word in keywords


@pytest.mark.parametrize(
    "title, text",
    [
        ("Anthropic tells California governor courts should be able to block risky AI models", "Policy and courts."),
        ("Expanding our partnership with GSA to bring its models to all levels of government", "Government rollout."),
        ("Can we trust LLMs to judge whether a research idea is novel?", "A benchmark of research ideas."),
        ("Genie 4: a new generation of world simulation", "Video game worlds."),
    ],
)
def test_general_ai_news_is_filtered_out_before_analysis(keywords, title, text):
    assert not matches_topics(item(title, text), keywords)


@pytest.mark.parametrize(
    "title, text",
    [
        ("OpenAI launches a new realtime voice model", "Lower latency speech."),
        ("Deepgram ships Flux speech-to-text update", "Streaming transcription."),
        ("Google adds Gemini Live to its voice mode", "Conversations by voice."),
        ("Twilio launches a voice agent builder", "Phone calls."),
        ("New voice cloning model from ElevenLabs", "Clones a voice."),
        ("LiveKit adds turn detection", "Barge-in handling."),
        ("townbox/ava (Space)", "Talk face to face with LFM3-Omni, running in your browser"),
        ("Qwen releases an Omni model", "Speech in, speech out."),
    ],
)
def test_voice_and_conversational_ai_news_passes(keywords, title, text):
    assert matches_topics(item(title, text), keywords)


@pytest.mark.parametrize(
    "title, url",
    [
        ("- LiveKit Cloud", "https://cloud.livekit.io/projects/new"),
        ("Acme TTS alternative for voice agents", "https://acme.example/blog"),
        ("Acme versus Beta", "https://acme.example/vs/beta"),
        ("One Voice Agent API", "https://deepgram.com/product/voice-agents"),
        ("Medical speech-to-text", "https://deepgram.com/solutions/medical"),
        ("The most accurate speech to text API", "https://acme.example/stt"),
        ("The speech to text API ranked #1 for streaming accuracy", "https://acme.example/speech-to-text-api"),
        ("AtomicChat/Transcribe-30B-GGUF (automatic-speech-recognition model)", "https://huggingface.co/AtomicChat/Transcribe-30B-GGUF"),
        ("nvidia/Transcribe-30B-NVFP4 (automatic-speech-recognition model)", "https://huggingface.co/nvidia/Transcribe-30B-NVFP4"),
        ("acme/voice-small-mlx (text-to-speech model)", "https://huggingface.co/acme/voice-small-mlx"),
    ],
)
def test_evergreen_and_junk_pages_are_excluded(title, url):
    import re

    patterns = [re.compile(p, re.IGNORECASE) for p in load_channel(CHANNEL).exclude]

    assert any(p.search(f"{title} {url}") for p in patterns)


def test_real_news_is_not_excluded():
    import re

    patterns = [re.compile(p, re.IGNORECASE) for p in load_channel(CHANNEL).exclude]
    texts = [
        "Deepgram ships Flux update https://deepgram.com/learn/flux-update",
        "Pipecat v1.15.0 https://github.com/pipecat-ai/pipecat/releases/tag/v1.15.0",
        "Introducing the realtime API https://openai.com/index/introducing-realtime-api",
        "Acme voice model ranked #1 on the TTS arena https://acme.example/blog/tts-arena",
        "empero-ai/PiVo-1.4M (text-to-speech model) https://huggingface.co/empero-ai/PiVo-1.4M",
        "nvidia/NVIDIA-NemotronLabs-RE-USE (audio-to-audio model) https://huggingface.co/nvidia/NVIDIA-NemotronLabs-RE-USE",
    ]

    assert not any(p.search(text) for text in texts for p in patterns)


def test_huggingface_voice_models_pass_the_topic_filter(keywords):
    from datetime import datetime, timezone

    from radar.filters import matches_topics
    from radar.huggingface import fetch_models
    from radar.models import Source

    now = datetime(2026, 11, 3, tzinfo=timezone.utc)
    source = Source("HF", "https://huggingface.co/api/models", 4, kind="huggingface")
    listing = [
        {"id": "empero-ai/PiVo-1.4M", "createdAt": "2026-11-01T21:54:14.000Z", "likes": 36,
         "pipeline_tag": "text-to-speech", "tags": ["onnx", "text-to-speech"]},
        {"id": "nvidia/NVIDIA-NemotronLabs-RE-USE", "createdAt": "2026-10-30T12:52:19.000Z", "likes": 133,
         "pipeline_tag": "audio-to-audio", "tags": ["speech-enhancement"]},
        {"id": "acme/image-gen", "createdAt": "2026-11-01T00:00:00.000Z", "likes": 90,
         "pipeline_tag": "text-to-image", "tags": ["diffusers"]},
    ]

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return listing

    items = fetch_models(source, get=lambda url, **kw: Response(), now=now)

    assert [matches_topics(i, keywords) for i in items] == [True, True, False]


def test_sources_file_follows_trending_huggingface_voice_models():
    from radar.config import load_sources

    sources = load_sources(CHANNEL.parent.parent / "sources.yaml").sources
    hf = [s for s in sources if s.kind == "huggingface"]

    models = [s for s in hf if s.url.startswith("https://huggingface.co/api/models?")]
    spaces = [s for s in hf if s.url.startswith("https://huggingface.co/api/spaces?")]

    assert len(models) >= 3 and len(spaces) == 1
    assert len(models) + len(spaces) == len(hf)
    assert all(s.min_likes >= 30 and s.max_age_days <= 14 for s in hf)
    assert all(s.tier == 4 and not s.discovery for s in hf)
    assert all("sort=trendingScore" in s.url for s in hf)
    assert "full=true" in spaces[0].url
    tasks = " ".join(s.url for s in models)
    for tag in ("text-to-speech", "automatic-speech-recognition", "audio-to-audio"):
        assert f"pipeline_tag={tag}" in tasks


def test_a_community_page_found_through_discovery_is_not_badged_official():
    from radar.config import load_sources
    from radar.filters import resolve_tier

    cfg = load_sources(CHANNEL.parent.parent / "sources.yaml")
    shared = Item(
        title="Show HN: a small TTS model",
        url="https://huggingface.co/someone/small-tts",
        text="",
        published=None,
        source="Hacker News",
        tier=3,
        discovery=True,
    )

    assert resolve_tier(shared, cfg) == 4


def test_the_ava_space_passes_the_topic_filter_end_to_end(keywords):
    from radar.huggingface import fetch_models
    from radar.models import Source

    now = datetime(2026, 11, 3, tzinfo=timezone.utc)
    source = Source("HF: Spaces", "https://huggingface.co/api/spaces?sort=trendingScore&full=true", 4, kind="huggingface", min_likes=30)
    listing = [
        {"id": "townbox/ava", "createdAt": "2026-10-30T12:09:18.000Z", "likes": 31,
         "cardData": {"title": "Ava", "short_description": "Talk face to face with LFM3-Omni, running in your browser"}},
        {"id": "briaai/Fibo-2.0-editing", "createdAt": "2026-10-30T12:09:18.000Z", "likes": 207,
         "cardData": {"title": "FIBO 2.0 Edit Turbo", "short_description": "Fibo 2.0 Edit Turbo image editing in 4 steps"}},
    ]

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return listing

    items = fetch_models(source, get=lambda url, **kw: Response(), now=now)

    assert [matches_topics(i, keywords) for i in items] == [True, False]
