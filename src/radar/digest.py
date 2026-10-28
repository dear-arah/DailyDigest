from __future__ import annotations

from datetime import datetime
from typing import Sequence

# Five fields at these limits plus the title and description stay under Discord's 6000-character embed total.
NAME_LIMIT = 150
VALUE_LIMIT = 1000
_ELLIPSIS = "…"
_COLOR = 0x5865F2


def _field_value(rec: dict) -> str:
    header = f"{rec['tag']} · {rec['product']} · {rec['score']}/10"
    link = f"[Source]({rec['url']})"
    blurb = f"{rec['summary']} **Agora angle:** {rec['angle']}"
    room = max(VALUE_LIMIT - len(header) - len(link) - 2, 0)
    if len(blurb) > room:
        blurb = blurb[: max(room - 1, 0)].rstrip() + _ELLIPSIS
    return f"{header}\n{blurb}\n{link}"


def build_digest(records: Sequence[dict], now: datetime, top: int = 5) -> dict | None:
    if not records:
        return None
    ranked = sorted(records, key=lambda r: r["score"], reverse=True)[:top]
    fields = [
        {"name": f"{rank}. {rec['title']}"[:NAME_LIMIT], "value": _field_value(rec)}
        for rank, rec in enumerate(ranked, start=1)
    ]
    return {
        "title": f"Daily digest · {now:%B} {now.day}, {now.year}",
        "description": "Top items from the last 24 hours, with a ready-to-paste blurb for each.",
        "color": _COLOR,
        "fields": fields,
    }
