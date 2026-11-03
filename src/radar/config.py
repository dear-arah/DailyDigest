from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from radar.models import Channel, ProviderSpec, Source


SOURCE_KINDS = ("feed", "huggingface")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SourcesConfig:
    sources: tuple[Source, ...]
    trusted_domains: dict[str, int]


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    return data


def _require(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise ConfigError(f"{where}: missing '{key}'")
    return data[key]


def _tier(value: Any, where: str) -> int:
    if value not in (1, 2, 3, 4):
        raise ConfigError(f"{where}: tier must be 1, 2, 3 or 4, got {value!r}")
    return value


def _kind(value: Any, where: str) -> str:
    if value not in SOURCE_KINDS:
        raise ConfigError(f"{where}: kind must be one of {', '.join(SOURCE_KINDS)}, got {value!r}")
    return value


def _source(entry: dict[str, Any], where: str) -> Source:
    return Source(
        name=_require(entry, "name", where),
        url=_require(entry, "url", where),
        tier=_tier(_require(entry, "tier", where), where),
        discovery=bool(entry.get("discovery", False)),
        kind=_kind(entry.get("kind", "feed"), where),
        min_likes=int(entry.get("min_likes", 0)),
        max_age_days=int(entry.get("max_age_days", 21)),
    )


def load_sources(path: Path) -> SourcesConfig:
    data = _read_yaml(path)
    sources = tuple(_source(entry, str(path)) for entry in _require(data, "sources", str(path)))
    trusted = {
        str(domain): _tier(tier, f"{path}: trusted_domains[{domain}]")
        for domain, tier in (data.get("trusted_domains") or {}).items()
    }
    return SourcesConfig(sources=sources, trusted_domains=trusted)


def load_channel(path: Path) -> Channel:
    data = _read_yaml(path)
    where = str(path)
    providers = tuple(
        ProviderSpec(
            name=_require(p, "name", where),
            model=_require(p, "model", where),
        )
        for p in _require(data, "providers", where)
    )
    if not providers:
        raise ConfigError(f"{where}: providers must not be empty")
    exclude = tuple(data.get("exclude") or ())
    for pattern in exclude:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigError(f"{where}: invalid exclude pattern {pattern!r}: {exc}") from exc
    return Channel(
        name=_require(data, "name", where),
        webhook_env=_require(data, "webhook_env", where),
        sources_file=_require(data, "sources_file", where),
        context_file=_require(data, "context_file", where),
        keywords=tuple(_require(data, "keywords", where)),
        threshold=int(_require(data, "threshold", where)),
        max_posts_per_run=int(_require(data, "max_posts_per_run", where)),
        max_age_hours=int(_require(data, "max_age_hours", where)),
        providers=providers,
        exclude=exclude,
    )
