from orders import calculate_order_total


def test_single_item_no_discount():
    total = calculate_order_total([{"name": "widget", "quantity": 1}])
    assert total == 10.79


def test_multi_item_with_discount():
    items = [{"name": "gizmo", "quantity": 3}, {"name": "widget", "quantity": 1}]
    total = calculate_order_total(items, discount_percent=33)
    assert total == 14.46


def test_multi_item_larger_order_with_discount():
    items = [{"name": "gizmo", "quantity": 4}, {"name": "gadget", "quantity": 4}]
    total = calculate_order_total(items, discount_percent=37)
    assert total == 49.76
