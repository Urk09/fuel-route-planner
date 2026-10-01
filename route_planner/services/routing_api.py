"""Gets the driving route from OpenRouteService: one call per trip."""

from dataclasses import dataclass

import requests
from django.conf import settings

from route_planner.services.location_resolver import Place


class RoutingError(Exception):
    """The routing service couldn't give us a route (down, slow, bad key, quota used up)."""


class NoRouteFound(RoutingError):
    """The service works, but there is no road route between the two places."""


@dataclass(frozen=True)
class Route:
    points: list[tuple[float, float]]  # (latitude, longitude) along the road
    distance_miles: float
    duration_hours: float


class OpenRouteServiceClient:
    """Talks to OpenRouteService. Holds the API key, so a test can pass a fake client instead."""

    PROFILE = "driving-car"  # a truck would be "driving-hgv" (Phase 2)
    URL = f"https://api.openrouteservice.org/v2/directions/{PROFILE}/geojson"
    TIMEOUT_SECONDS = 20
    METERS_PER_MILE = 1609.344
    SECONDS_PER_HOUR = 3600

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else settings.OPEN_ROUTE_SERVICE_API_KEY

    def get_route(self, start: Place, finish: Place) -> Route:
        """One call: the road from start to finish, kept inside the US."""
        if not self.api_key:
            raise RoutingError("OPEN_ROUTE_SERVICE_API_KEY is missing from .env.")

        response = self._send(start, finish)
        self._check_status(response)
        return self._to_route(response.json())

    def _send(self, start: Place, finish: Place) -> requests.Response:
        body = {
            # ORS wants [longitude, latitude].
            "coordinates": [[start.longitude, start.latitude], [finish.longitude, finish.latitude]],
            "instructions": False,  # we don't need turn-by-turn text
            "options": {"avoid_borders": "all"},  # stay inside the US
        }
        try:
            return requests.post(
                self.URL,
                json=body,
                headers={"Authorization": self.api_key},
                timeout=self.TIMEOUT_SECONDS,
            )
        except requests.Timeout as exc:
            raise RoutingError("The routing service took too long to answer. Try again.") from exc
        except requests.RequestException as exc:
            raise RoutingError("Could not reach the routing service.") from exc

    @staticmethod
    def _check_status(response: requests.Response) -> None:
        if response.status_code == 200:
            return
        if response.status_code == 404:
            raise NoRouteFound("No driving route was found between these places.")
        if response.status_code in (401, 403):
            raise RoutingError("The routing service rejected the API key (wrong key, or today's quota is used up).")
        if response.status_code == 429:
            raise RoutingError("Too many routing requests right now. Wait a minute and try again.")
        raise RoutingError(f"The routing service failed (HTTP {response.status_code}).")

    def _to_route(self, data: dict) -> Route:
        feature = data["features"][0]
        coordinates = feature["geometry"]["coordinates"]
        summary = feature["properties"]["summary"]
        return Route(
            points=[(latitude, longitude) for longitude, latitude in coordinates],
            distance_miles=summary["distance"] / self.METERS_PER_MILE,
            duration_hours=summary["duration"] / self.SECONDS_PER_HOUR,
        )