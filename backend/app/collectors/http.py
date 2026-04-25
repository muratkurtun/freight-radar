"""HTTP fetching for HTML collectors.

One place to configure the User-Agent, timeouts and retry policy so every
collector fetches the same way. Uses `requests` with urllib3's built-in
Retry adapter for idempotent failures (429 + 5xx) and exponential backoff.

Not covered here (intentionally):
  - JavaScript-rendered pages. If a target site needs a real browser,
    add a sibling module (e.g. `playwright_fetch.py`) and a new collector
    that uses it. Do not teach this module about Playwright.
  - Robots.txt / polite crawling rules. Add when we take on sources that
    require it; for now we only crawl sources an operator has opted in to.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.logging import get_logger

logger = get_logger(__name__)

USER_AGENT = "OpportunityRadar/0.1 (+https://opportunityradar.local)"
DEFAULT_TIMEOUT = 20.0
DEFAULT_RETRIES = 3
BACKOFF_FACTOR = 0.5  # sleeps 0.5s, 1.0s, 2.0s between retries
RETRY_STATUS: tuple[int, ...] = (429, 500, 502, 503, 504)


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en,tr;q=0.8",
        }
    )
    retry = Retry(
        total=DEFAULT_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS,
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


@contextmanager
def session_scope() -> Iterator[requests.Session]:
    """Open a pooled Session for one collection run; close on exit."""
    session = _build_session()
    try:
        yield session
    finally:
        session.close()


def fetch_html(
    session: requests.Session,
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> str | None:
    """GET `url` and return the response body, or None on any HTTP error.

    Any networking / HTTP error is logged and swallowed: one failed detail
    page should never take down an entire collection batch."""
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Fetch failed for %s: %s", url, e)
        return None
    return resp.text
