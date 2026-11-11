"""Tests for the legacy exporter."""

from legacy import format_legacy_report


def test_legacy_report():
    text = format_legacy_report([("alpha", 10), ("beta", 20)])
    assert "alpha" in text and "beta" in text
    assert "30.00" in text
