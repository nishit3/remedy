"""Order total calculation: subtotal -> discount -> tax."""

from catalog import get_price
from pricing import apply_discount, line_item_total
from utils import round_money

TAX_RATE = 0.08


def calculate_order_total(items: list[dict], discount_percent: float = 0) -> float:
    """items: [{"name": str, "quantity": int}, ...]"""
    subtotal = 0.0
    for item in items:
        price = get_price(item["name"])
        subtotal += line_item_total(item["quantity"], price)

    subtotal = apply_discount(subtotal, discount_percent)
    tax = round_money(subtotal * TAX_RATE)
    return round_money(subtotal + tax)
