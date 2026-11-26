def calculate_total(prices: list[float], discount_percent: float) -> float:
    if not 0 <= discount_percent <= 100:
        raise ValueError("Discount must be between 0 and 100")
    total = sum(prices)
    return total * (1 - discount_percent / 100)