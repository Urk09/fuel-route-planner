import math
from dataclasses import dataclass

from route_planner.models import FuelStation
from route_planner.services.routing_api import Route
from route_planner.services.geo import distance_miles

SEARCH_RADIUS_MILES = 10.0
# A grid square must be at least SEARCH_RADIUS_MILES wide everywhere in the US.
# East-west degrees are narrowest at the northern border (49° N): about 45 miles per degree.
NARROWEST_MILES_PER_DEGREE = 45.0
GRID_CELL_DEGREES = SEARCH_RADIUS_MILES / NARROWEST_MILES_PER_DEGREE  # about 0.22°


@dataclass(frozen=True)
class StationOnRoute:
    station: FuelStation
    mile_marker: float                # trip-meter reading where the station is reached
    off_route_miles: float            # distance from the station to the road
    route_point: tuple[float, float]  # closest road point (lat, lon): where its map marker goes


def grid_cell(point: tuple[float, float]) -> tuple[int, int]:
    """Which grid square (pigeonhole) a (lat, lon) point falls in."""
    
    return math.floor(point[0] / GRID_CELL_DEGREES), math.floor(point[1] / GRID_CELL_DEGREES)

def mile_markers(points: list[tuple[float, float]]) -> list[float]:
    """Running total of distance along the route: the 'trip meter' reading at each point."""
    
    markers = [0.0]
    
    for previous, current in zip(points, points[1:]):
        markers.append(markers[-1] + distance_miles(previous, current))
    
    return markers

def find_stations_near_route(route: Route, stations: list[FuelStation]) -> list[StationOnRoute]:
    """Stations within SEARCH_RADIUS_MILES of the road, sorted by mile marker."""
    
    markers = mile_markers(route.points)

    # 1. Sort every road point into its grid square, once.
    squares = {}
    
    for index, point in enumerate(route.points):
        squares.setdefault(grid_cell(point), []).append(index)

    found = []
    for station in stations:
        position = (station.latitude, station.longitude)
        row, col = grid_cell(position)

        # 2. Only the road points in this square and the 8 around it.
        nearby = [
            index
            for d_row in (-1, 0, 1)
            for d_col in (-1, 0, 1)
            for index in squares.get((row + d_row, col + d_col), [])
        ]
        
        if not nearby:
            continue  # no road anywhere near this station: skip it

        # 3. Measure only those, and keep the station if the closest is within the limit.
        off_route, closest = min((distance_miles(position, route.points[i]), i) for i in nearby)
        
        if off_route <= SEARCH_RADIUS_MILES:
            found.append(StationOnRoute(station, markers[closest], off_route, route.points[closest]))

    return sorted(found, key=lambda item: item.mile_marker)