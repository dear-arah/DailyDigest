from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from radar.config import load_channel, load_sources
from radar.dedupe import SeenStore
from radar.llm.chain import build_chain
from radar.run import run_channel, run_digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="radar", description="Scheduled tech news for Discord")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("run", "collect, analyze and post new items"), ("digest", "post the daily digest")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--channel", type=Path, required=True, help="path to a channel yaml file")
        command.add_argument("--state", type=Path, help="path to the state json file")
        command.add_argument("--dry-run", action="store_true", help="print embeds instead of posting")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    channel = load_channel(args.channel)
    state = args.state or Path("state") / f"{channel.name}.json"
    store = SeenStore(state)
    webhook_url = os.environ.get(channel.webhook_env)
    now = datetime.now(timezone.utc)

    if not args.dry_run and not webhook_url:
        print(f"error: {channel.webhook_env} is not set", file=sys.stderr)
        return 2

    if args.command == "digest":
        posted = run_digest(store, webhook_url, now, dry_run=args.dry_run)
        print("digest posted" if posted else "nothing to post")
        return 0

    cfg = load_sources(Path(channel.sources_file))
    context = Path(channel.context_file).read_text()
    chain = build_chain(channel.providers, os.environ)
    if not chain.providers:
        logging.warning("no LLM provider has a key; items will post as 'analysis pending'")
    report = run_channel(
        channel,
        cfg,
        context=context,
        store=store,
        chain=chain,
        now=now,
        webhook_url=webhook_url,
        dry_run=args.dry_run,
    )
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
