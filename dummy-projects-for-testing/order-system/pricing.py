"""Line-item pricing and discount application."""

from utils import round_money


def line_item_total(quantity: int, unit_price: float) -> float:
    return round_money(unit_price * quantity)


def apply_discount(amount: float, discount_percent: float) -> float:
    return round_money(amount - amount * discount_percent / 100)
