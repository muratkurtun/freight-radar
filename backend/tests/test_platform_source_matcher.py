"""Tests for `matches_preferences` — the canonical spec for how a
platform source is selected for a tenant. The repo's SQL `&&` overlap
must agree with this Python predicate; if you change one you must
change the other."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

from app.repositories.platform_sources import matches_preferences


@dataclass
class _Source:
    """Minimal Source-shaped object — avoids importing the SQLAlchemy
    model so the unit test stays DB-free."""
    is_active: bool = True
    tenant_id: UUID | None = None
    region_tags: list[str] = field(default_factory=list)
    sector_tags: list[str] = field(default_factory=list)
    customer_type_tags: list[str] = field(default_factory=list)
    signal_focus_tags: list[str] = field(default_factory=list)


@dataclass
class _Prefs:
    is_active: bool = True
    regions: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    target_customer_types: list[str] = field(default_factory=list)
    signal_focuses: list[str] = field(default_factory=list)
    minimum_confidence: Decimal = Decimal("0")


def _full_match() -> tuple[_Source, _Prefs]:
    """Source + prefs that overlap on every dimension — flip one thing
    in the test to see what makes it fail."""
    return (
        _Source(
            region_tags=["TR", "EU"],
            sector_tags=["logistics"],
            customer_type_tags=["smb"],
            signal_focus_tags=["warehouse_opening"],
        ),
        _Prefs(
            regions=["TR"],
            sectors=["logistics"],
            target_customer_types=["smb"],
            signal_focuses=["warehouse_opening"],
        ),
    )


def test_full_overlap_matches():
    source, prefs = _full_match()
    assert matches_preferences(source, prefs) is True


def test_partial_miss_on_any_dimension_excludes():
    """Each dimension must overlap independently. Missing on a single
    dimension is enough to exclude the source."""
    for missing in ("regions", "sectors", "target_customer_types", "signal_focuses"):
        source, prefs = _full_match()
        setattr(prefs, missing, ["something_else"])
        assert matches_preferences(source, prefs) is False, (
            f"Should have failed when {missing} did not overlap"
        )


def test_empty_source_tag_excludes_no_wildcard():
    """Per product strategy: an empty source tag list never matches.
    A platform admin must populate every dimension before the source is
    selectable."""
    for dim in ("region_tags", "sector_tags", "customer_type_tags", "signal_focus_tags"):
        source, prefs = _full_match()
        setattr(source, dim, [])
        assert matches_preferences(source, prefs) is False


def test_empty_preference_dim_excludes():
    """Symmetrically: a tenant who hasn't picked any value on a
    dimension matches no source on that dimension."""
    for dim in ("regions", "sectors", "target_customer_types", "signal_focuses"):
        source, prefs = _full_match()
        setattr(prefs, dim, [])
        assert matches_preferences(source, prefs) is False


def test_inactive_source_excluded():
    source, prefs = _full_match()
    source.is_active = False
    assert matches_preferences(source, prefs) is False


def test_inactive_preference_excludes_everything():
    source, prefs = _full_match()
    prefs.is_active = False
    assert matches_preferences(source, prefs) is False


def test_legacy_tenant_source_excluded():
    """Legacy tenant-scoped rows (tenant_id NOT NULL) must never be
    picked up by the platform matching path."""
    source, prefs = _full_match()
    source.tenant_id = uuid4()
    assert matches_preferences(source, prefs) is False
