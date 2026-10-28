from __future__ import annotations

import json
import logging

from radar.filters import badge
from radar.llm.chain import FallbackChain
from radar.llm.providers import AllProvidersFailed
from radar.models import TAGS, Analysis, Item

log = logging.getLogger(__name__)

SUMMARY_LIMIT = 600
ANGLE_LIMIT = 400

_SYSTEM = """You help the developer community lead at Agora keep up with tech news.

Rules:
- Use only facts present in the item text you are given. If the text does not support a claim, say so instead of guessing.
- Never invent Agora capabilities beyond the context below.
- Reply with a single JSON object and nothing else, with these keys:
  summary: 2-3 sentences on what happened.
  score: integer 0-10 for relevance to Agora (10 = needs action now).
  tag: one of {tags}.
  product: the Agora product most affected, or "General".
  angle: 1-2 sentences on what this means for Agora: a competitive threat to a named product, an opportunity, or an integration idea.

Agora context:
{context}"""


class AnalysisError(ValueError):
    pass


def build_messages(item: Item, context: str) -> tuple[str, str]:
    system = _SYSTEM.format(tags=", ".join(TAGS), context=context)
    published = item.published.isoformat() if item.published else "unknown"
    user = (
        f"Source: {item.source} (trust: {badge(item.tier)})\n"
        f"Title: {item.title}\n"
        f"URL: {item.url}\n"
        f"Published: {published}\n\n"
        f"Text:\n{item.text}"
    )
    return system, user


def parse_analysis(raw: str) -> Analysis:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise AnalysisError("no JSON object in model output")
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError as exc:
        raise AnalysisError(f"invalid JSON: {exc}") from exc

    try:
        summary, tag, product, angle = (str(data[k]).strip() for k in ("summary", "tag", "product", "angle"))
        score = int(data["score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AnalysisError(f"missing or invalid field: {exc}") from exc

    if tag not in TAGS:
        raise AnalysisError(f"unknown tag: {tag!r}")

    return Analysis(
        summary=summary[:SUMMARY_LIMIT],
        score=max(0, min(10, score)),
        tag=tag,
        product=product,
        angle=angle[:ANGLE_LIMIT],
    )


def analyze(item: Item, chain: FallbackChain, context: str) -> Analysis | None:
    system, user = build_messages(item, context)
    try:
        return chain.complete(system, user, parse=parse_analysis)
    except AllProvidersFailed:
        log.warning("analysis unavailable for %s", item.url)
        return None
