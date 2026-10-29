from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable

from radar.analyze import analyze
from radar.collect import collect_all
from radar.config import SourcesConfig
from radar.dedupe import SeenStore, normalize_url, title_key
from radar.digest import build_digest
from radar.filters import is_fresh, matches_topics, resolve_tier
from radar.llm.chain import FallbackChain
from radar.models import Channel
from radar.post import build_embed, post_embed
from radar.resolve import resolve_url

log = logging.getLogger(__name__)

ANALYSIS_FACTOR = 3
MAX_UNANALYZED_PER_RUN = 2
# Seconds between model calls, to stay under free-tier per-minute limits.
ANALYSIS_PAUSE = 3.0


@dataclass
class RunReport:
    collected: int = 0
    new: int = 0
    posted: int = 0
    pending: int = 0
    skipped_untrusted: int = 0
    failed: int = 0


def _compile_exclusions(channel: Channel) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in channel.exclude]


def _is_excluded(item, patterns: list[re.Pattern]) -> bool:
    text = f"{item.title} {item.url}"
    return any(p.search(text) for p in patterns)


def _select_candidates(items, cfg: SourcesConfig, channel: Channel, store: SeenStore, now: datetime, report: RunReport):
    new = [item for item in items if not store.seen(item)]
    report.new = len(new)

    excluded = _compile_exclusions(channel)
    candidates = []
    in_batch: set[str] = set()
    for item in new:
        if not is_fresh(item, now, channel.max_age_hours) or not matches_topics(item, channel.keywords):
            continue
        if _is_excluded(item, excluded):
            continue
        tier = resolve_tier(item, cfg)
        if tier is None:
            report.skipped_untrusted += 1
            continue
        keys = {normalize_url(item.url), title_key(item.title)}
        if keys & in_batch:
            continue
        in_batch |= keys
        candidates.append((item, tier))

    candidates.sort(key=lambda c: (c[1], -(c[0].published.timestamp() if c[0].published else 0)))
    return candidates[: channel.max_posts_per_run * ANALYSIS_FACTOR]


def run_channel(
    channel: Channel,
    cfg: SourcesConfig,
    *,
    context: str,
    store: SeenStore,
    chain: FallbackChain,
    now: datetime,
    collect: Callable = collect_all,
    post: Callable = post_embed,
    resolve: Callable[[str], str] = resolve_url,
    sleep: Callable[[float], None] = time.sleep,
    webhook_url: str | None,
    dry_run: bool = False,
) -> RunReport:
    if webhook_url is None and not dry_run:
        raise ValueError("a webhook url is required unless dry_run is set")

    report = RunReport()
    items = collect(cfg.sources)
    report.collected = len(items)
    try:
        if store.is_empty() and not dry_run:
            for item in items:
                store.record(item, None, posted=False, now=now)
            report.new = len(items)
            return report

        to_post = []
        for index, (item, tier) in enumerate(_select_candidates(items, cfg, channel, store, now, report)):
            if index:
                sleep(ANALYSIS_PAUSE)
            try:
                analysis = analyze(item, chain, context)
            except Exception:
                log.exception("skipping %s after unexpected error", item.url)
                continue
            if analysis is not None and analysis.score < channel.threshold:
                if not dry_run:
                    store.record(item, analysis, posted=False, now=now)
                continue
            to_post.append((item, analysis, tier))

        to_post.sort(key=lambda entry: -(entry[1].score if entry[1] else channel.threshold))
        selected = []
        unanalyzed = 0
        for entry in to_post:
            if len(selected) == channel.max_posts_per_run:
                break
            if entry[1] is None:
                if entry[2] != 1 or unanalyzed >= MAX_UNANALYZED_PER_RUN:
                    continue
                unanalyzed += 1
            selected.append(entry)

        excluded = _compile_exclusions(channel)
        for item, analysis, tier in selected:
            shown = replace(item, url=resolve(item.url))
            if _is_excluded(shown, excluded):
                # Only visible after resolving a search-result link (for example a product page).
                if not dry_run:
                    store.record(item, analysis, posted=False, now=now, url=shown.url)
                continue
            embed = build_embed(shown, analysis, tier)
            if dry_run:
                print(json.dumps(embed, indent=2))
                delivered = True
            else:
                delivered = post(webhook_url, embed)
                store.record(item, analysis, posted=delivered, now=now, retry=not delivered, url=shown.url)
            if delivered:
                report.posted += 1
                if analysis is None:
                    report.pending += 1
            else:
                report.failed += 1
        return report
    finally:
        if not dry_run:
            store.prune(now)
            store.save()


def run_digest(
    store: SeenStore,
    webhook_url: str | None,
    now: datetime,
    post: Callable = post_embed,
    dry_run: bool = False,
) -> str:
    embed = build_digest(store.recent_posted(now, hours=24), now)
    if embed is None:
        return "empty"
    if dry_run:
        print(json.dumps(embed, indent=2))
        return "posted"
    return "posted" if post(webhook_url, embed) else "failed"
