from dataclasses import dataclass

import requests
from django.conf import settings

from route_planner.services.location_resolver import Place

ORS_PROFILE = "driving-car"  # "driving-hgv" for trucks
ORS_URL = f"https://api.openrouteservice.org/v2/directions/{ORS_PROFILE}/geojson"
METERS_PER_MILE = 1609.344


class RoutingError(Exception):
    """The route couldn't be fetched (missing key, no road route, service down...)."""

class NoRouteFound(RoutingError):
    """There is no driving route between the two places."""


@dataclass(frozen=True)
class Route:
    points: list[tuple[float, float]]  # (latitude, longitude) along the road, start to finish
    distance_miles: float
    duration_hours: float


def get_route(start: Place, finish: Place) -> Route:
    """Ask OpenRouteService for the driving route between two places. Exactly one API call."""
    
    if not settings.OPEN_ROUTE_SERVICE_API_KEY:
        raise RoutingError("OPEN_ROUTE_SERVICE_API_KEY is not set.")

    body = {
        # ORS wants [longitude, latitude]; our Place stores latitude first.
        "coordinates": [
            [start.longitude, start.latitude],
            [finish.longitude, finish.latitude],
        ],
        "instructions": False,
        "options": {"avoid_borders": "all"},  # never cross into Canada or Mexico
    }

    try:
        response = requests.post(
            ORS_URL,
            json=body,
            headers={"Authorization": settings.OPEN_ROUTE_SERVICE_API_KEY},
            timeout=30,
        )
    except requests.Timeout as exc:
        raise RoutingError("The routing service took too long to answer. Please try again.") from exc
    except requests.RequestException as exc:
        raise RoutingError("Could not reach the routing service. Please try again later.") from exc

    if response.status_code == 404:
        raise NoRouteFound("No driving route was found between these two places.")
    
    if response.status_code in (401, 403):
        raise RoutingError("The routing service rejected the request: check the API key or today's quota.")
    
    if response.status_code == 429:
        raise RoutingError("Too many routing requests in a short time. Please wait a minute and retry.")
    
    if response.status_code != 200:
        raise RoutingError(f"Routing service error {response.status_code}: {response.text}")

    feature = response.json()["features"][0]
    summary = feature["properties"]["summary"]
    points = [(lat, lon) for lon, lat in feature["geometry"]["coordinates"]]

    return Route(
        points=points,
        distance_miles=summary["distance"] / METERS_PER_MILE,
        duration_hours=summary["duration"] / 3600,
    )