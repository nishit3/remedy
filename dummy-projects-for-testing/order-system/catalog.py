"""Product catalog -- prices in USD."""

CATALOG = {
    "widget": 9.99,
    "gadget": 14.95,
    "gizmo": 3.33,
}


def get_price(item_name: str) -> float:
    if item_name not in CATALOG:
        raise KeyError(f"unknown item: {item_name}")
    return CATALOG[item_name]
