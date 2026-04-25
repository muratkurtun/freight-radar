"""Google News / generic RSS collector.

Source.url is any RSS or Atom feed — the most common case for us is a
Google News query feed like:

    https://news.google.com/rss/search?q=warehouse+opens&hl=en

Source.config keys (all optional):
  - limit: int (default 25) — max entries per collection run.
  - fetch_detail: bool (default False) — if True, follow entry.link and
    extract article text from the target page. Off by default because
    Google News redirects go through an interstitial that many publishers
    render with JavaScript; enable only for direct publisher feeds.
  - detail_content_selector: str — CSS selector for the article body on
    the detail page (used when fetch_detail=True).

This collector only produces candidate SourceItems. It does NOT decide
whether anything is a freight/logistics signal — that is the detector's
job further down the pipeline.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
from time import mktime
from typing import Any

import feedparser
import requests

from app.collectors.base import BaseCollector, SourceItem
from app.collectors.extract import html_to_text
from app.collectors.http import fetch_html, session_scope
from app.collectors.normalize import clean_text, clean_title, strip_tracking
from app.core.hashing import content_hash
from app.core.logging import get_logger
from app.domain.enums import SourceType
from app.domain.models import Source

logger = get_logger(__name__)

DEFAULT_LIMIT = 25


class NewsCollector(BaseCollector):
    source_type = SourceType.NEWS.value

    def collect(self, source: Source) -> list[SourceItem]:
        cfg = source.config or {}
        limit = int(cfg.get("limit", DEFAULT_LIMIT))
        fetch_detail = bool(cfg.get("fetch_detail", False))
        detail_sel: str | None = cfg.get("detail_content_selector")

        feed = feedparser.parse(source.url)
        if feed.bozo:
            logger.warning(
                "Feed parse error for %s: %s", source.url, feed.bozo_exception
            )

        session_cm = session_scope() if fetch_detail else nullcontext()
        items: list[SourceItem] = []
        seen_hashes: set[str] = set()

        with session_cm as session:
            for entry in feed.entries[:limit]:
                item = _entry_to_item(
                    entry,
                    session=session,
                    detail_sel=detail_sel,
                )
                if item is None:
                    continue
                chash = content_hash(title=item.title, content=item.content)
                if chash in seen_hashes:
                    continue
                seen_hashes.add(chash)
                items.append(item)
        return items


def _entry_to_item(
    entry: Any,
    *,
    session: requests.Session | None,
    detail_sel: str | None,
) -> SourceItem | None:
    external_id = entry.get("id") or entry.get("link")
    if not external_id:
        return None

    link = entry.get("link")
    url = strip_tracking(link) if link else None
    title = clean_title(entry.get("title"))
    content = clean_text(
        entry.get("summary") or entry.get("description") or entry.get("title") or ""
    )

    if session is not None and url:
        html = fetch_html(session, url)
        if html:
            detail = html_to_text(html, selector=detail_sel)
            if detail:
                content = clean_text(detail)

    return SourceItem(
        external_id=str(external_id),
        title=title,
        url=url,
        content=content,
        published_at=_parse_published(entry),
    )


def _parse_published(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
