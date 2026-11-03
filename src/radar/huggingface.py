from __future__ import annotations

import logging
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlsplit

import requests

from radar.models import Item, Source

log = logging.getLogger(__name__)

TEXT_LIMIT = 2000
MAX_TAGS = 12
USER_AGENT = "daily-digest/0.1 (+https://github.com/dear-arah/DailyDigest)"

# First path segments on huggingface.co that are not a model owner.
_NOT_AN_OWNER = {
    "api", "blog", "collections", "datasets", "docs", "learn", "models",
    "organizations", "papers", "posts", "spaces",
}
_FRONT_MATTER = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_SPACE = re.compile(r"\s+")


def _created(entry: dict) -> datetime:
    return datetime.fromisoformat(entry["createdAt"].replace("Z", "+00:00"))


def _describe(entry: dict) -> str:
    model_id = entry["id"]
    task = entry.get("pipeline_tag")
    tags = [t for t in entry.get("tags") or [] if ":" not in t][:MAX_TAGS]
    licenses = [t.split(":", 1)[1] for t in entry.get("tags") or [] if t.startswith("license:")]
    owner = model_id.split("/", 1)[0]
    parts = [f"Model {model_id}, uploaded to the Hugging Face Hub by {owner}. Hugging Face only hosts it."]
    if task:
        parts.append(f"Task: {task}.")
    if tags:
        parts.append(f"Tags: {', '.join(tags)}.")
    if licenses:
        parts.append(f"License: {licenses[0]}.")
    parts.append(f"{entry.get('likes', 0)} likes, {entry.get('downloads', 0)} downloads.")
    return " ".join(parts)


def fetch_models(
    source: Source,
    get: Callable = requests.get,
    now: datetime | None = None,
    timeout: float = 15,
) -> list[Item]:
    """Read a Hugging Face model listing (for example the trending text-to-speech models).

    The listing carries no publication date, so an item is dated when it is first seen.
    Models older than the source's max_age_days or with fewer likes than min_likes are dropped.
    """
    now = now or datetime.now(timezone.utc)
    response = get(source.url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    cutoff = now - timedelta(days=source.max_age_days)

    items = []
    for entry in response.json():
        try:
            created = _created(entry)
            title = f"{entry['id']} ({entry.get('pipeline_tag') or 'model'} model)"
            text = _describe(entry)
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        if entry.get("likes", 0) < source.min_likes or created < cutoff:
            continue
        items.append(
            Item(
                title=title,
                url=f"https://huggingface.co/{entry['id']}",
                text=text,
                published=now,
                source=source.name,
                tier=source.tier,
            )
        )
    return items


def _is_model_page(url: str) -> bool:
    parts = urlsplit(url)
    segments = [s for s in parts.path.split("/") if s]
    return parts.hostname == "huggingface.co" and len(segments) == 2 and segments[0] not in _NOT_AN_OWNER


def enrich(item: Item, get: Callable = requests.get, timeout: float = 15) -> Item:
    """Append the model card to a Hugging Face model item so the analysis has real content.

    Any other item, or a card that cannot be read, is returned unchanged.
    """
    if not _is_model_page(item.url):
        return item
    try:
        response = get(
            f"{item.url.rstrip('/')}/raw/main/README.md",
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except Exception as exc:
        log.warning("model card unavailable for %s: %s", item.url, exc)
        return item
    card = _SPACE.sub(" ", _FRONT_MATTER.sub("", response.text)).strip()[:TEXT_LIMIT]
    if not card:
        return item
    return replace(item, text=f"{item.text} {card}")
