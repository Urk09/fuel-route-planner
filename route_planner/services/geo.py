import math

EARTH_RADIUS_MILES = 3958.8


def distance_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Straight-line ("as the crow flies") distance in miles between two (lat, lon) points."""
    
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)

    # haversine formula
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))