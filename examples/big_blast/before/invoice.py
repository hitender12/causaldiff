"""Invoices rendered from the cart."""

from cart import cart_total
from pricing import price_of


def render_invoice(cart):
    """One-line invoice summary for a cart."""
    return f"Invoice total: {cart_total(cart)}"


def invoice_lines(cart):
    """One priced line per item in the cart."""
    return [f"{item['name']}: {price_of(item)}" for item in cart]
