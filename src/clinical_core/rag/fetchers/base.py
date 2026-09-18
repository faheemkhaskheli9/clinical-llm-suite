"""Shared HTTP helpers for medical-reference fetchers.

Ported from clinical-ai-assistant's src/rag/fetchers/base.py (issue #13).
Every fetcher goes through a session built here so retry/backoff, timeouts,
and an identifying User-Agent (the source APIs ask callers to send one) are
consistent, and so raw responses can be cached to disk before parsing.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "clinical-llm-suite-portfolio-project/0.1 (public-dataset ingestion)"
DEFAULT_TIMEOUT = 30


class ResponseValidationError(RuntimeError):
    """A response was HTTP 200 but its body failed the caller's validity check.

    Raised instead of caching the body, so a maintenance page / truncated
    payload served with a 200 status never poisons ``data/raw/``.
    """


def build_session() -> requests.Session:
    """A requests.Session with retry/backoff on transient errors and a real UA."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/xml, */*"})
    retry = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_text(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    *,
    cache_path: Path | None = None,
    validate: Callable[[str], bool] | None = None,
) -> tuple[str, bool]:
    """Like :func:`get_text` but also returns whether the body came from cache.

    Returns ``(text, from_cache)``. Callers use ``from_cache`` to skip the
    inter-request politeness delay when no network call was actually made.

    ``validate``, if given, is called with the body text and must return True
    for it to be considered usable. It is applied to BOTH freshly fetched and
    cached bodies:

    * a cached file that no longer validates (e.g. an error page cached by an
      older run) is discarded and re-fetched rather than returned;
    * a freshly fetched body that fails validation raises
      ``ResponseValidationError`` and is NOT written to the cache, so a bad
      HTTP 200 can't brick every subsequent run.
    """
    if cache_path is not None and cache_path.exists():
        cached = cache_path.read_text(encoding="utf-8")
        if validate is None or validate(cached):
            return cached, True
        cache_path.unlink(missing_ok=True)  # stale/poisoned cache entry

    response = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    text = response.text
    if validate is not None and not validate(text):
        raise ResponseValidationError(f"response body from {url} failed validation ({len(text)} chars)")
    if cache_path is not None:
        cache_path.write_text(text, encoding="utf-8")
    return text, False


def get_text(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    *,
    cache_path: Path | None = None,
    validate: Callable[[str], bool] | None = None,
) -> str:
    """GET a URL as text, using ``cache_path`` as a read-through cache.

    See :func:`fetch_text` for the ``validate`` semantics.
    """
    text, _ = fetch_text(session, url, params, cache_path=cache_path, validate=validate)
    return text


def get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    """GET a URL and parse it as JSON. Not cached — used for paginated listings."""
    response = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_bytes(session: requests.Session, url: str, *, cache_path: Path) -> bytes:
    """GET a URL's raw bytes (e.g. a zip archive), caching to ``cache_path``."""
    if cache_path.exists():
        return cache_path.read_bytes()
    response = session.get(url, timeout=DEFAULT_TIMEOUT * 4, stream=True)
    response.raise_for_status()
    data = response.content
    cache_path.write_bytes(data)
    return data


def polite_delay(seconds: float = 0.34) -> None:
    """Small pause between paginated calls (~3 req/s) to stay well under rate limits."""
    time.sleep(seconds)
