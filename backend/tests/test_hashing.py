"""Hashing behaviour tests.

These hashes are the dedupe primary keys (UNIQUE constraints in the DB);
any change to the normalization rules silently changes dedupe scope, so
the regression tests here are intentionally explicit.
"""
from app.core.hashing import content_hash, signal_hash


def test_content_hash_is_deterministic():
    a = content_hash(title="Hello", content="World")
    b = content_hash(title="Hello", content="World")
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_content_hash_normalizes_whitespace_and_case():
    base = content_hash(title="Hello", content="World wide")
    same = content_hash(title="  HELLO  ", content="World    Wide")
    assert base == same


def test_content_hash_distinguishes_distinct_inputs():
    assert content_hash(title="A", content="B") != content_hash(title="A", content="C")
    assert content_hash(title="A", content="B") != content_hash(title="B", content="A")


# --- signal_hash (post-0005 four-input shape) ----------------------------

def test_signal_hash_includes_all_fields():
    base = signal_hash(
        signal_type="export_expansion",
        company_name="Acme",
        region="eu",
        target_customer_type="exporter",
    )
    different_company = signal_hash(
        signal_type="export_expansion",
        company_name="Globex",
        region="eu",
        target_customer_type="exporter",
    )
    different_region = signal_hash(
        signal_type="export_expansion",
        company_name="Acme",
        region="turkey",
        target_customer_type="exporter",
    )
    different_segment = signal_hash(
        signal_type="export_expansion",
        company_name="Acme",
        region="eu",
        target_customer_type="distributor",
    )
    assert base != different_company
    assert base != different_region
    assert base != different_segment


def test_signal_hash_treats_none_and_empty_equivalently():
    a = signal_hash(
        signal_type="new_warehouse",
        company_name="Acme",
        region=None,
        target_customer_type=None,
    )
    b = signal_hash(
        signal_type="new_warehouse",
        company_name="Acme",
        region="",
        target_customer_type="",
    )
    assert a == b
