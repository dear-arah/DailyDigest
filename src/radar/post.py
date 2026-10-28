from __future__ import annotations

import logging
import time
from typing import Callable

import requests

from radar.filters import badge
from radar.models import Analysis, Item

log = logging.getLogger(__name__)

TITLE_LIMIT = 256
DESCRIPTION_LIMIT = 4096
MAX_RETRY_WAIT = 30.0

_COLORS = {
    "threat": 0xE74C3C,
    "opportunity": 0x2ECC71,
    "integration": 0x3498DB,
    "fyi": 0x95A5A6,
}
_PENDING_COLOR = 0x7F8C8D


def build_embed(item: Item, analysis: Analysis | None, tier: int) -> dict:
    if analysis is None:
        description = f"**Analysis pending**\n\n{item.text[:600]}"
        color = _PENDING_COLOR
    else:
        description = (
            f"**{analysis.tag.upper()}** · {analysis.product} · {analysis.score}/10\n\n"
            f"{analysis.summary}\n\n"
            f"**Agora angle:** {analysis.angle}"
        )
        color = _COLORS[analysis.tag]

    embed = {
        "title": item.title[:TITLE_LIMIT],
        "url": item.url,
        "description": description[:DESCRIPTION_LIMIT],
        "color": color,
        "footer": {"text": f"{badge(tier)} · {item.source}"},
    }
    if item.published:
        embed["timestamp"] = item.published.isoformat()
    return embed


def post_embed(
    webhook_url: str,
    embed: dict,
    post: Callable = requests.post,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    for attempt in range(2):
        try:
            response = post(webhook_url, json={"embeds": [embed]}, timeout=15)
        except Exception as exc:
            log.warning("discord post failed: %s", exc)
            return False

        if 200 <= response.status_code < 300:
            return True
        if response.status_code == 429 and attempt == 0:
            wait = float(response.json().get("retry_after", 1))
            sleep(min(wait, MAX_RETRY_WAIT))
            continue
        log.warning("discord returned HTTP %s", response.status_code)
        return False
    return False
