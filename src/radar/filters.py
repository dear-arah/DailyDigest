from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Sequence
from urllib.parse import urlsplit

from radar.config import SourcesConfig
from radar.models import Item

_BADGES = {1: "Official", 2: "Known voice", 3: "Press"}


def is_fresh(item: Item, now: datetime, max_age_hours: int) -> bool:
    if item.published is None:
        return True
    return now - item.published <= timedelta(hours=max_age_hours)


def matches_topics(item: Item, keywords: Sequence[str]) -> bool:
    haystack = f"{item.title} {item.text}"
    return any(
        re.search(rf"\b{re.escape(kw)}s?\b", haystack, re.IGNORECASE) for kw in keywords
    )


def _domain(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def resolve_tier(item: Item, cfg: SourcesConfig) -> int | None:
    if not item.discovery:
        return item.tier
    domain = _domain(item.publisher_url or item.url)
    matches = [
        (trusted, tier)
        for trusted, tier in cfg.trusted_domains.items()
        if domain == trusted or domain.endswith(f".{trusted}")
    ]
    if not matches:
        return None
    return max(matches, key=lambda m: len(m[0]))[1]


def badge(tier: int) -> str:
    return _BADGES[tier]
