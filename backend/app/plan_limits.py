"""Лимиты тарифных планов."""

PLAN_LIMITS = {
    "free": {
        "bookings_per_month": 30,
        "history_days":       30,
        "export":             False,
        "locations":          1,
    },
    "standard": {
        "bookings_per_month": None,
        "history_days":       180,
        "export":             True,
        "locations":          1,
    },
    "pro": {
        "bookings_per_month": None,
        "history_days":       730,
        "export":             True,
        "locations":          5,
    },
}