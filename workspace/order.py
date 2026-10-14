def calculate_total(prices: list[float], discount_percent: float) -> float:
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("Discount percentage must be between 0 and 100")
    return sum(prices) * (1 - discount_percent / 100)