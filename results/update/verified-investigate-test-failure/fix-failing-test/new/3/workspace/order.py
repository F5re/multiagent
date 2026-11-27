def calculate_total(prices: list[float], discount_percent: float) -> float:
    total = sum(prices)
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("Discount percent must be between 0 and 100")
    return total - (total * discount_percent / 100)
