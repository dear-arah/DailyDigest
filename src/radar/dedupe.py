from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from radar.models import Analysis, Item

_TRACKING_PARAMS = {"fbclid", "gclid", "ref", "ref_src", "mc_cid", "mc_eid"}
_NON_ALNUM = re.compile(r"[^a-z0-9]")


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.startswith("utm_") and k not in _TRACKING_PARAMS
    )
    return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/"), urlencode(query), ""))


def title_key(title: str) -> str:
    return _NON_ALNUM.sub("", title.lower())


class SeenStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._records: dict[str, dict] = self._load()
        self._titles: dict[str, str] = {}
        self._reindex()

    def _load(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        records = data.get("records") if isinstance(data, dict) else None
        return records if isinstance(records, dict) else {}

    def _reindex(self) -> None:
        self._titles = {title_key(r.get("title", "")): url for url, r in self._records.items()}

    def is_empty(self) -> bool:
        return not self._records

    def seen(self, item: Item) -> bool:
        key = normalize_url(item.url)
        record = self._records.get(key) or self._records.get(self._titles.get(title_key(item.title), ""))
        return record is not None and not record.get("retry", False)

    def record(
        self,
        item: Item,
        analysis: Analysis | None,
        posted: bool,
        now: datetime,
        retry: bool = False,
        url: str | None = None,
    ) -> None:
        key = normalize_url(item.url)
        self._records[key] = {
            "title": item.title,
            "url": url or item.url,
            "source": item.source,
            "tier": item.tier,
            "ts": now.isoformat(),
            "posted": posted,
            "retry": retry,
            "summary": analysis.summary if analysis else "",
            "score": analysis.score if analysis else 0,
            "tag": analysis.tag if analysis else "",
            "product": analysis.product if analysis else "",
            "angle": analysis.angle if analysis else "",
        }
        self._titles[title_key(item.title)] = key

    def recent_posted(self, now: datetime, hours: int = 24) -> list[dict]:
        cutoff = now - timedelta(hours=hours)
        return [
            dict(r)
            for r in self._records.values()
            if r["posted"] and datetime.fromisoformat(r["ts"]) >= cutoff
        ]

    def prune(self, now: datetime, days: int = 30) -> None:
        cutoff = now - timedelta(days=days)
        self._records = {
            url: r for url, r in self._records.items() if datetime.fromisoformat(r["ts"]) >= cutoff
        }
        self._reindex()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"records": self._records}, indent=2, sort_keys=True))
