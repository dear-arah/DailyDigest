from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from typing import Callable, Iterable

import feedparser
import requests

from radar.models import Item, Source

log = logging.getLogger(__name__)

TEXT_LIMIT = 2000
USER_AGENT = "daily-digest/0.1 (+https://github.com/dear-arah/DailyDigest)"

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_BARE_VERSION = re.compile(r"^v?\d+(\.\d+)+\S*$")


class FeedError(Exception):
    pass


def _clean(raw: str) -> str:
    text = html.unescape(_TAG.sub(" ", raw))
    return _SPACE.sub(" ", text).strip()[:TEXT_LIMIT]


def _published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def _body(entry) -> str:
    if entry.get("summary"):
        return entry["summary"]
    content = entry.get("content")
    return content[0].get("value", "") if content else ""


def fetch_feed(source: Source, get: Callable = requests.get, timeout: float = 15) -> list[Item]:
    try:
        response = get(source.url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except Exception as exc:
        raise FeedError(f"{source.name}: {exc}") from exc

    parsed = feedparser.parse(response.content)
    items = []
    for entry in parsed.entries:
        link = entry.get("link")
        if not link:
            continue
        title = _clean(entry.get("title", ""))
        if _BARE_VERSION.match(title):
            title = f"{source.name} {title}"
        items.append(
            Item(
                title=title,
                url=link,
                text=_clean(_body(entry)),
                published=_published(entry),
                source=source.name,
                tier=source.tier,
                discovery=source.discovery,
                publisher_url=(entry.get("source") or {}).get("href"),
            )
        )
    return items


def collect_all(sources: Iterable[Source], get: Callable = requests.get) -> list[Item]:
    items: list[Item] = []
    for source in sources:
        try:
            items.extend(fetch_feed(source, get=get))
        except FeedError as exc:
            log.warning("skipping feed: %s", exc)
    return items
