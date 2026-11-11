"""Checkout: discounts and order totals."""

from cart import cart_total


def apply_discount(cart, pct):
    """Cart total after a percentage discount."""
    total = cart_total(cart)
    return round(total * (1 - pct), 2)


def checkout(cart, pct=0.0):
    """Complete a purchase and return the order summary."""
    total = apply_discount(cart, pct)
    return {"total": total, "items": len(cart)}
