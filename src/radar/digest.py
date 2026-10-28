from __future__ import annotations

from datetime import datetime
from typing import Sequence

NAME_LIMIT = 256
VALUE_LIMIT = 1024
_COLOR = 0x5865F2


def build_digest(records: Sequence[dict], now: datetime, top: int = 5) -> dict | None:
    if not records:
        return None
    ranked = sorted(records, key=lambda r: r["score"], reverse=True)[:top]
    fields = []
    for rank, rec in enumerate(ranked, start=1):
        value = (
            f"[Source]({rec['url']}) · {rec['tag']} · {rec['product']} · {rec['score']}/10\n"
            f"{rec['summary']} **Agora angle:** {rec['angle']}"
        )
        fields.append(
            {
                "name": f"{rank}. {rec['title']}"[:NAME_LIMIT],
                "value": value[:VALUE_LIMIT],
            }
        )
    return {
        "title": f"Daily digest · {now:%B} {now.day}, {now.year}",
        "description": "Top items from the last 24 hours, with a ready-to-paste blurb for each.",
        "color": _COLOR,
        "fields": fields,
    }
