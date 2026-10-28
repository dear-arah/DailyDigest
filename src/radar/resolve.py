from __future__ import annotations

import json
import logging
import re
from typing import Callable
from urllib.parse import quote, urlsplit

import requests

log = logging.getLogger(__name__)

_GOOGLE_NEWS = "news.google.com"
_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; radar/0.1)"}
_SIGNATURE = re.compile(r'data-n-a-sg="([^"]+)"')
_TIMESTAMP = re.compile(r'data-n-a-ts="([^"]+)"')


def _is_google_news(url: str) -> bool:
    return urlsplit(url).netloc.lower() == _GOOGLE_NEWS


def _request_body(article_id: str, signature: str, timestamp: str) -> str:
    inner = (
        '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
        f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{article_id}",{timestamp},"{signature}"]'
    )
    return "f.req=" + quote(json.dumps([[["Fbv4je", inner, None, "generic"]]]))


def _parse_answer(text: str) -> str | None:
    try:
        outer = json.loads(text.split("\n", 1)[1])
        for row in outer:
            if row[0] == "wrb.fr" and row[2]:
                url = json.loads(row[2])[1]
                if isinstance(url, str) and url.startswith("http") and not _is_google_news(url):
                    return url
    except (IndexError, KeyError, TypeError, ValueError):
        return None
    return None


def resolve_url(url: str, get: Callable = requests.get, post: Callable = requests.post) -> str:
    """Turn a Google News redirect link into the publisher's own URL.

    Any other URL is returned untouched. If Google changes the page or blocks the request, the
    original link is returned, which still opens the article.
    """
    if not _is_google_news(url):
        return url

    article_id = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    try:
        page = get(f"https://{_GOOGLE_NEWS}/rss/articles/{article_id}", headers=_HEADERS, timeout=15)
        if page.status_code != 200:
            return url
        signature, timestamp = _SIGNATURE.search(page.text), _TIMESTAMP.search(page.text)
        if not (signature and timestamp):
            return url
        answer = post(
            _BATCH_URL,
            data=_request_body(article_id, signature.group(1), timestamp.group(1)),
            headers={**_HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            timeout=15,
        )
        if answer.status_code != 200:
            return url
    except requests.RequestException as exc:
        log.warning("could not resolve %s: %s", url, exc)
        return url
    return _parse_answer(answer.text) or url
