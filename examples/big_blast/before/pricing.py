"""Pricing: tax-inclusive prices for the shop."""

TAX_RATE = 0.20


def price_of(item):
    """Base price of an item, tax included."""
    return round(item["price"] * (1 + TAX_RATE), 2)
