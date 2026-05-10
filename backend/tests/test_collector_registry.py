"""Collector registry contract tests.

Phase 12.5 introduced `news_html` as a new SourceType that reuses the
existing CompanyWebsiteCollector at the registry level. The mapping
is one of those things that's easy to break silently in a refactor;
these tests pin the per-type dispatch so a mis-wired registry fails
loud."""
from __future__ import annotations

import pytest

from app.collectors import registry
from app.collectors.company_website_collector import CompanyWebsiteCollector
from app.collectors.job_board_collector import JobBoardCollector
from app.collectors.news_collector import NewsCollector
from app.core.errors import AppError
from app.domain.enums import SourceType


def test_registry_returns_news_collector_for_news():
    assert isinstance(
        registry.get_collector(SourceType.NEWS.value), NewsCollector
    )


def test_registry_returns_company_website_collector_for_company_website():
    assert isinstance(
        registry.get_collector(SourceType.COMPANY_WEBSITE.value),
        CompanyWebsiteCollector,
    )


def test_registry_returns_job_board_collector_for_job_board():
    assert isinstance(
        registry.get_collector(SourceType.JOB_BOARD.value),
        JobBoardCollector,
    )


def test_registry_reuses_company_website_collector_for_news_html():
    """Phase 12.5 contract: `news_html` and `company_website` share
    the same collector class. The semantic split lives in the enum
    and in analytics, NOT in the collector code."""
    a = registry.get_collector(SourceType.NEWS_HTML.value)
    b = registry.get_collector(SourceType.COMPANY_WEBSITE.value)
    assert isinstance(a, CompanyWebsiteCollector)
    assert isinstance(b, CompanyWebsiteCollector)
    assert type(a) is type(b)


def test_registry_covers_every_source_type():
    """Every SourceType value must resolve to a collector. Catches
    the case where a new enum entry is added without updating the
    registry — the runtime would otherwise raise AppError on the
    first matched source of that type."""
    for st in SourceType:
        collector = registry.get_collector(st.value)
        assert collector is not None


def test_registry_raises_for_unknown_source_type():
    with pytest.raises(AppError):
        registry.get_collector("not_a_real_type")
