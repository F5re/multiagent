def calculate_total(prices: list[float], discount_percent: float) -> float:
    total = sum(prices)
    if not (0 <= discount_percent <= 100):
        raise ValueError(f"discount must be between 0 and 100, got {discount_percent}")
    return total - total * discount_percent / 100