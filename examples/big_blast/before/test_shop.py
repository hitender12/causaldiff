"""Tests for the shop. Every test here depends on pricing, directly or not."""

from cart import cart_total
from checkout import apply_discount, checkout
from invoice import render_invoice
from pricing import price_of


def test_price_of():
    assert price_of({"price": 100}) == 120.0


def test_cart_total():
    assert cart_total([{"price": 100}]) == 120.0


def test_checkout():
    assert checkout([{"price": 100}])["total"] == 120.0


def test_discount():
    assert apply_discount([{"price": 100}], 0.1) == 108.0


def test_invoice():
    assert "120.0" in render_invoice([{"price": 100}])
