"""Shopping cart totals."""

from pricing import price_of


def cart_total(cart):
    """Total price of all items in the cart, tax included."""
    return round(sum(price_of(item) for item in cart), 2)


def item_count(cart):
    """Number of items in the cart."""
    return len(cart)
