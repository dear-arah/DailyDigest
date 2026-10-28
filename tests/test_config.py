from pathlib import Path

import pytest

from radar.config import ConfigError, load_channel, load_sources
from radar.models import ProviderSpec, Source


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def test_load_sources_parses_tiers_and_trusted_domains(tmp_path):
    path = write(
        tmp_path,
        "sources.yaml",
        """
sources:
  - {name: Vendor Blog, url: "https://vendor.example/feed.xml", tier: 1}
  - {name: HN, url: "https://hnrss.org/newest", tier: 3, discovery: true}
trusted_domains:
  vendor.example: 1
  press.example: 3
""",
    )

    cfg = load_sources(path)

    assert cfg.sources == (
        Source("Vendor Blog", "https://vendor.example/feed.xml", 1, False),
        Source("HN", "https://hnrss.org/newest", 3, True),
    )
    assert cfg.trusted_domains == {"vendor.example": 1, "press.example": 3}


def test_load_sources_rejects_tier_4(tmp_path):
    path = write(
        tmp_path,
        "sources.yaml",
        "sources:\n  - {name: Bad, url: 'https://x.example/f', tier: 4}\n",
    )

    with pytest.raises(ConfigError):
        load_sources(path)


def test_load_channel_reads_providers_in_order(tmp_path):
    path = write(
        tmp_path,
        "news.yaml",
        """
name: news
webhook_env: DISCORD_WEBHOOK_URL
sources_file: config/sources.yaml
context_file: config/agora-context.md
keywords: [voice ai, agents]
threshold: 6
max_posts_per_run: 8
max_age_hours: 48
providers:
  - {name: github, model: openai/gpt-4.1-mini}
  - {name: gemini, model: gemini-2.5-flash}
""",
    )

    channel = load_channel(path)

    assert channel.name == "news"
    assert channel.keywords == ("voice ai", "agents")
    assert channel.providers == (
        ProviderSpec("github", "openai/gpt-4.1-mini"),
        ProviderSpec("gemini", "gemini-2.5-flash"),
    )
    assert channel.threshold == 6


def test_load_channel_missing_webhook_env_raises(tmp_path):
    path = write(
        tmp_path,
        "news.yaml",
        """
name: news
sources_file: a
context_file: b
keywords: [x]
threshold: 6
max_posts_per_run: 8
max_age_hours: 48
providers:
  - {name: github, model: m}
""",
    )

    with pytest.raises(ConfigError):
        load_channel(path)


CHANNEL_YAML = """
name: news
webhook_env: DISCORD_WEBHOOK_URL
sources_file: s
context_file: c
keywords: [voice ai]
threshold: 6
max_posts_per_run: 8
max_age_hours: 48
{extra}
providers:
  - {{name: gemini, model: m}}
"""


def test_load_channel_reads_exclude_patterns(tmp_path):
    path = write(tmp_path, "news.yaml", CHANNEL_YAML.format(extra="exclude: ['\\balternatives?\\b', '/vs/']"))

    assert load_channel(path).exclude == (r"\balternatives?\b", "/vs/")


def test_load_channel_exclude_defaults_to_empty(tmp_path):
    path = write(tmp_path, "news.yaml", CHANNEL_YAML.format(extra=""))

    assert load_channel(path).exclude == ()


def test_load_channel_rejects_invalid_exclude_pattern(tmp_path):
    path = write(tmp_path, "news.yaml", CHANNEL_YAML.format(extra="exclude: ['(unclosed']"))

    with pytest.raises(ConfigError):
        load_channel(path)
