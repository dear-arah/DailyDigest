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
        ("Expanding our partnership with GSA to bring Claude to all levels of government", "Government rollout."),
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
    ],
)
def test_evergreen_and_junk_pages_are_excluded(title, url):
    import re

    patterns = [re.compile(p, re.IGNORECASE) for p in load_channel(CHANNEL).exclude]

    assert any(p.search(f"{title} {url}") for p in patterns)


def test_real_news_is_not_excluded():
    import re

    patterns = [re.compile(p, re.IGNORECASE) for p in load_channel(CHANNEL).exclude]
    text = "Deepgram ships Flux update https://deepgram.com/learn/flux-update"

    assert not any(p.search(text) for p in patterns)
