def calculate_total(prices: list[float], discount_percent: float) -> float:
    if not 0 <= discount_percent <= 100:
        raise ValueError("Discount percent must be between 0 and 100")
    return sum(prices) - (sum(prices) * discount_percent / 100)
