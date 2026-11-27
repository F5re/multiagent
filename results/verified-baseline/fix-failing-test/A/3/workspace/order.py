def calculate_total(prices: list[float], discount_percent: float) -> float:
    total = sum(prices)
    if not (0 <= discount_percent <= 100):
        raise ValueError("Discount must be between 0 and 100")
    return total - (total * discount_percent / 100)