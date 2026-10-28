from __future__ import annotations

import logging
from typing import Callable, Mapping, Sequence

import requests

from radar.llm.providers import (
    AllProvidersFailed,
    GeminiProvider,
    OpenAICompatProvider,
    Provider,
    ProviderError,
)
from radar.models import ProviderSpec

log = logging.getLogger(__name__)

_GITHUB_BASE = "https://models.github.ai/inference"
_GROQ_BASE = "https://api.groq.com/openai/v1"
_KEY_ENV = {"github": "GITHUB_TOKEN", "gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}


class FallbackChain:
    def __init__(self, providers: Sequence[Provider]):
        self.providers = list(providers)

    def complete(self, system: str, user: str) -> str:
        for provider in self.providers:
            try:
                return provider.complete(system, user)
            except ProviderError as exc:
                log.warning("provider %s failed: %s", provider.name, exc)
        raise AllProvidersFailed("no provider produced a response")


def build_chain(
    specs: Sequence[ProviderSpec],
    env: Mapping[str, str],
    post: Callable = requests.post,
) -> FallbackChain:
    providers: list[Provider] = []
    for spec in specs:
        if spec.name not in _KEY_ENV:
            raise ValueError(f"unknown provider: {spec.name}")
        key = env.get(_KEY_ENV[spec.name])
        if not key:
            log.info("provider %s skipped: %s not set", spec.name, _KEY_ENV[spec.name])
            continue
        if spec.name == "gemini":
            providers.append(GeminiProvider(spec.model, key, post=post))
        else:
            base = _GITHUB_BASE if spec.name == "github" else _GROQ_BASE
            providers.append(OpenAICompatProvider(spec.name, base, spec.model, key, post=post))
    return FallbackChain(providers)
