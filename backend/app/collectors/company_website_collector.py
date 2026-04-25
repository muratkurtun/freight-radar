"""Static HTML company-website collector (press / news / blog pages).

Same shape and constraints as JobBoardCollector: it works on pages whose
list of entries is in the initial HTML response. Company "newsroom" and
"press" pages are usually static; blog pages often are too. SPA-rendered
newsrooms are NOT in scope here — add a Playwright variant if we need
one.

Source.url is the listing page (/news, /press, /blog, ...).
Source.config keys:
  - item_selector: CSS selector for each entry on the list page.
  - link_selector: CSS selector for the <a> inside the entry.
  - title_selector: CSS selector for the title inside the entry.
  - detail_content_selector (optional): CSS selector for the article
    body on the detail page. If omitted, the entry's own text is used
    as content.
  - limit (optional, default 25).
"""
from __future__ import annotations

from app.collectors.base import BaseCollector, SourceItem
from app.collectors.extract import html_to_text, node_href, node_text, parse_html
from app.collectors.http import fetch_html, session_scope
from app.collectors.normalize import absolutize, clean_text, clean_title
from app.core.hashing import content_hash
from app.core.logging import get_logger
from app.domain.enums import SourceType
from app.domain.models import Source

logger = get_logger(__name__)

DEFAULT_LIMIT = 25


class CompanyWebsiteCollector(BaseCollector):
    source_type = SourceType.COMPANY_WEBSITE.value

    def collect(self, source: Source) -> list[SourceItem]:
        cfg = source.config or {}
        item_sel = cfg.get("item_selector")
        link_sel = cfg.get("link_selector")
        title_sel = cfg.get("title_selector")
        detail_sel: str | None = cfg.get("detail_content_selector")
        limit = int(cfg.get("limit", DEFAULT_LIMIT))

        if not (item_sel and link_sel and title_sel):
            logger.warning("Source %s missing required selectors in config", source.id)
            return []

        with session_scope() as session:
            list_html = fetch_html(session, source.url)
            if list_html is None:
                return []

            soup = parse_html(list_html)
            entries = soup.select(item_sel)[:limit]

            items: list[SourceItem] = []
            seen_hashes: set[str] = set()
            for entry in entries:
                href = node_href(entry, link_sel)
                title = clean_title(node_text(entry, title_sel))
                if not href or not title:
                    continue
                detail_url = absolutize(source.url, href)
                if detail_url is None:
                    continue

                content = clean_text(entry.get_text(" ", strip=True))
                if detail_sel:
                    detail_html = fetch_html(session, detail_url)
                    if detail_html:
                        detail_content = html_to_text(detail_html, selector=detail_sel)
                        if detail_content:
                            content = clean_text(detail_content)

                chash = content_hash(title=title, content=content)
                if chash in seen_hashes:
                    continue
                seen_hashes.add(chash)

                items.append(
                    SourceItem(
                        external_id=detail_url,
                        title=title,
                        url=detail_url,
                        content=content,
                    )
                )
            return items
