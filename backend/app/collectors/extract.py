"""HTML → text extraction helpers used by the HTML collectors.

Keeps soup parsing in one place so every collector strips the same
boilerplate (scripts, styles, SVG, iframes) before handing text off to the
signal detector. The LLM layer later will still trim / truncate on its
own, but the crawler should not send raw <script> blobs across process
boundaries.
"""
from __future__ import annotations

from bs4 import BeautifulSoup, Tag

_DROP_TAGS: tuple[str, ...] = (
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "iframe",
    "form",
)


def parse_html(html: str) -> BeautifulSoup:
    """Parse an HTML document and strip boilerplate tags in place."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    return soup


def html_to_text(html: str, *, selector: str | None = None) -> str:
    """Return visible text from `html`.

    If `selector` is given, extract text from the first matching node only
    (useful for "article body" selectors on detail pages). Returns an
    empty string when nothing matches; the caller decides what to do."""
    soup = parse_html(html)
    node: Tag | BeautifulSoup | None = soup.select_one(selector) if selector else soup
    if node is None:
        return ""
    return node.get_text(" ", strip=True)


def node_text(parent: Tag, selector: str) -> str | None:
    """Return visible text from the first `selector` match inside `parent`."""
    node = parent.select_one(selector)
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def node_href(parent: Tag, selector: str) -> str | None:
    """Return the href of the first `selector` match inside `parent`."""
    node = parent.select_one(selector)
    if node is None:
        return None
    href = node.get("href")
    return href if isinstance(href, str) and href else None
