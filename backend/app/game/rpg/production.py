"""
Shared production calculation for buildings.
Lazy/pull-based: no periodic DB writes, just compute on demand.
"""
from datetime import datetime


def calculate_production(last_collected: datetime, production_rate: float,
                         storage_capacity: int) -> dict:
    """Calculate current production for a building.

    Returns dict with:
        produced: int - resources accumulated (capped at storage)
        fill_ratio: float - 0.0 to 1.0
        seconds_to_full: float - seconds until storage is full (-1 if full)
    """
    now = datetime.utcnow()
    hours_since = (now - last_collected).total_seconds() / 3600
    raw_produced = hours_since * production_rate

    cap = storage_capacity if storage_capacity > 0 else 999999
    produced = min(int(raw_produced), cap)

    fill_ratio = min(1.0, raw_produced / cap) if cap > 0 else 0.0

    if fill_ratio >= 1.0:
        seconds_to_full = -1
    elif production_rate > 0:
        remaining = cap - raw_produced
        seconds_to_full = (remaining / production_rate) * 3600
    else:
        seconds_to_full = -1

    return {
        "produced": produced,
        "fill_ratio": round(fill_ratio, 3),
        "seconds_to_full": round(seconds_to_full, 1),
    }
