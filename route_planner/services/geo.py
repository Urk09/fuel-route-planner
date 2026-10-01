"""Distances on the Earth's surface."""

import math


class Geo:
    """Earth maths. No settings to hold, so every method is static: call `Geo.distance_miles(...)`."""

    EARTH_RADIUS_MILES = 3958.8

    @staticmethod
    def distance_miles(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
        """Straight-line distance between two (latitude, longitude) points (the haversine formula)."""
        latitude_a, longitude_a = map(math.radians, point_a)
        latitude_b, longitude_b = map(math.radians, point_b)
        latitude_change = latitude_b - latitude_a
        longitude_change = longitude_b - longitude_a
        haversine = (
            math.sin(latitude_change / 2) ** 2
            + math.cos(latitude_a) * math.cos(latitude_b) * math.sin(longitude_change / 2) ** 2
        )
        return 2 * Geo.EARTH_RADIUS_MILES * math.asin(math.sqrt(haversine))