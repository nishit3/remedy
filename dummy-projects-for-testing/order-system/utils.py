"""Shared money helpers -- every dollar amount in the system should be
rounded through here so rounding behavior stays consistent."""

from decimal import Decimal, ROUND_HALF_UP


def round_money(amount: float) -> float:
    return float(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
