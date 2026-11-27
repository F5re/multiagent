def calculate_total(prices: list[float], discount_percent: float) -> float:
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("Discount must be between 0 and 100")
    return sum(prices) - sum(p * (discount_percent / 100.0) for p in prices)