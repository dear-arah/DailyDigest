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
- Score strictly; most items should score 5 or lower:
  9-10: a competitor, partner or platform ships or changes something in voice or conversational AI or real-time communication that Agora should respond to now.
  7-8: directly about voice or conversational AI: speech recognition, text-to-speech, real-time voice models, voice agents, telephony, WebRTC, or the agent platforms and standards used to build them.
  4-6: general AI platform or agent news with only an indirect link to voice.
  0-3: policy, legal, funding, hiring, general AI research or products with no voice or real-time link.
- Marketing comparison pages ("X alternative", "A vs B") and evergreen landing pages are not news: score them 3 or lower unless the text announces something new.
- Never speculate about effects on Agora's customers or product availability unless the text says so. If the link to Agora is weak, say that plainly in angle and score 4 or lower.
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


def _text(data: dict, key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


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
        summary, tag, product, angle = (_text(data, k) for k in ("summary", "tag", "product", "angle"))
        score = int(data["score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AnalysisError(f"missing or invalid field: {exc}") from exc

    tag = tag.lower()
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
