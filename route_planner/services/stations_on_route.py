"""Finds the fuel stations near a route, and how far along the route each one is."""

import math
from dataclasses import dataclass

from route_planner.models import FuelStation
from route_planner.services.geo import Geo
from route_planner.services.routing_api import Route


@dataclass(frozen=True)
class StationOnRoute:
    station: FuelStation
    mile_marker: float  # how far along the route the station is
    off_route_miles: float  # how far the station is from the road
    route_point: tuple[float, float]  # the road point closest to the station


class StationFinder:
    """Grid search: put every route point into a square, then check only the squares around each station."""

    SEARCH_RADIUS_MILES = 10.0
    # One degree of longitude is shortest at the US's northern edge (49°N): about 45 miles.
    NARROWEST_MILES_PER_DEGREE = 45.0

    def __init__(self, search_radius_miles: float = SEARCH_RADIUS_MILES):
        self.search_radius_miles = search_radius_miles
        # A square is at least as wide as the search radius, so the 3x3 squares around a station cover it.
        self.square_size_degrees = search_radius_miles / self.NARROWEST_MILES_PER_DEGREE

    def find_near_route(self, route: Route, stations) -> list[StationOnRoute]:
        """Every station within the search radius of the road, ordered by mile marker."""
        mile_markers = self.mile_markers(route.points)
        squares = self._route_points_by_square(route.points)

        found = []
        for station in stations:
            station_point = (station.latitude, station.longitude)
            nearby_point_indexes = self._indexes_in_surrounding_squares(squares, station_point)
            if not nearby_point_indexes:
                continue

            distance, closest_index = min(
                (Geo.distance_miles(station_point, route.points[index]), index)
                for index in nearby_point_indexes
            )
            if distance <= self.search_radius_miles:
                found.append(
                    StationOnRoute(
                        station=station,
                        mile_marker=mile_markers[closest_index],
                        off_route_miles=distance,
                        route_point=route.points[closest_index],
                    )
                )

        return sorted(found, key=lambda item: item.mile_marker)

    @staticmethod
    def mile_markers(points: list[tuple[float, float]]) -> list[float]:
        """Running total of distance: how many miles along the route each point is."""
        markers = [0.0]
        for previous_point, current_point in zip(points, points[1:]):
            markers.append(markers[-1] + Geo.distance_miles(previous_point, current_point))
        return markers

    def _square(self, point: tuple[float, float]) -> tuple[int, int]:
        """Which grid square a point falls in."""
        latitude, longitude = point
        return (
            math.floor(latitude / self.square_size_degrees),
            math.floor(longitude / self.square_size_degrees),
        )

    def _route_points_by_square(self, points: list[tuple[float, float]]) -> dict[tuple[int, int], list[int]]:
        """Square -> the indexes of the route points inside it."""
        squares: dict[tuple[int, int], list[int]] = {}
        for index, point in enumerate(points):
            squares.setdefault(self._square(point), []).append(index)
        return squares

    def _indexes_in_surrounding_squares(self, squares, point: tuple[float, float]) -> list[int]:
        """Route point indexes in the station's square and the 8 squares around it."""
        row, column = self._square(point)
        indexes = []
        for row_offset in (-1, 0, 1):
            for column_offset in (-1, 0, 1):
                indexes.extend(squares.get((row + row_offset, column + column_offset), []))
        return indexes