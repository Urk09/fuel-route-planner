"""Remembers routes in Redis, so a repeat trip doesn't call OpenRouteService again."""

import logging

from django.core.cache import cache
from redis.exceptions import RedisError

from route_planner.services.location_resolver import Place
from route_planner.services.routing_api import OpenRouteServiceClient, Route

logger = logging.getLogger(__name__)


class CachedRoutingClient:
    """Wraps a routing client: Redis first, the real API only on a miss.

    It has the same `get_route()` as the client it wraps, so TripPlanner can't tell the difference.
    If Redis is down, it skips the cache and calls the API: the cache is a speed-up, never a reason to fail.
    """

    CACHE_SECONDS = 30 * 24 * 60 * 60  # 30 days: roads rarely change
    KEY_VERSION = "v1"  # change to "v2" if what we store ever changes; old entries are then ignored

    def __init__(self, routing_client: OpenRouteServiceClient | None = None):
        self.routing_client = routing_client or OpenRouteServiceClient()

    def get_route(self, start: Place, finish: Place) -> Route:
        key = self.cache_key(start, finish)

        route = self._read(key)
        if route is not None:
            return route

        route = self.routing_client.get_route(start, finish)  # if this fails, nothing is saved
        self._write(key, route)
        return route

    def cache_key(self, start: Place, finish: Place) -> str:
        """e.g. "route:v1:driving-car:41.83755,-87.68184:38.63570,-90.24458"."""
        return (
            f"route:{self.KEY_VERSION}:{self.routing_client.PROFILE}:"
            f"{start.latitude:.5f},{start.longitude:.5f}:"
            f"{finish.latitude:.5f},{finish.longitude:.5f}"
        )

    def _read(self, key: str) -> Route | None:
        try:
            return cache.get(key)
        except RedisError as error:
            logger.warning("Route cache unavailable, calling the routing API instead: %s", error)
            return None

    def _write(self, key: str, route: Route) -> None:
        try:
            cache.set(key, route, timeout=self.CACHE_SECONDS)
        except RedisError as error:
            logger.warning("Could not save the route in the cache: %s", error)