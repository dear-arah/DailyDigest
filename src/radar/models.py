from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

TAGS = ("threat", "opportunity", "integration", "fyi")


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    tier: int
    discovery: bool = False


@dataclass(frozen=True)
class Item:
    title: str
    url: str
    text: str
    published: datetime | None
    source: str
    tier: int
    discovery: bool = False
    publisher_url: str | None = None


@dataclass(frozen=True)
class Analysis:
    summary: str
    score: int
    tag: str
    product: str
    angle: str


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    model: str


@dataclass(frozen=True)
class Channel:
    name: str
    webhook_env: str
    sources_file: str
    context_file: str
    keywords: tuple[str, ...]
    threshold: int
    max_posts_per_run: int
    max_age_hours: int
    providers: tuple[ProviderSpec, ...]
    exclude: tuple[str, ...] = ()
