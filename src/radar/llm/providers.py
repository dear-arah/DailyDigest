from __future__ import annotations

import time
from typing import Callable, Protocol

import requests


class ProviderError(Exception):
    pass


class AllProvidersFailed(Exception):
    pass


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


_RETRY_STATUSES = (429, 503)
_DEFAULT_WAIT = 5.0
_MAX_WAIT = 15.0


def _retry_wait(response) -> float:
    try:
        wait = float(response.headers.get("Retry-After", _DEFAULT_WAIT))
    except (AttributeError, TypeError, ValueError):
        wait = _DEFAULT_WAIT
    return max(0.0, min(wait, _MAX_WAIT))


def _send(post: Callable, url: str, sleep: Callable[[float], None] = time.sleep, **kwargs) -> dict:
    """POST once, and once more after a short wait when the provider is rate limited or overloaded."""
    try:
        response = post(url, **kwargs)
        if response.status_code in _RETRY_STATUSES:
            sleep(_retry_wait(response))
            response = post(url, **kwargs)
        if response.status_code >= 400:
            raise ProviderError(f"HTTP {response.status_code} from {url}")
        return response.json()
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"request to {url} failed: {exc}") from exc


class OpenAICompatProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str,
        post: Callable = requests.post,
        timeout: float = 60,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._sleep = sleep
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._post = post
        self._timeout = timeout

    def complete(self, system: str, user: str) -> str:
        data = _send(
            self._post,
            f"{self._base_url}/chat/completions",
            sleep=self._sleep,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self._timeout,
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name}: unexpected response shape") from exc


class GeminiProvider:
    name = "gemini"
    _BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        model: str,
        api_key: str,
        post: Callable = requests.post,
        timeout: float = 60,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._sleep = sleep
        self._model = model
        self._api_key = api_key
        self._post = post
        self._timeout = timeout

    def complete(self, system: str, user: str) -> str:
        data = _send(
            self._post,
            f"{self._BASE}/{self._model}:generateContent",
            sleep=self._sleep,
            headers={"x-goog-api-key": self._api_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
            },
            timeout=self._timeout,
        )
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("gemini: unexpected response shape") from exc
