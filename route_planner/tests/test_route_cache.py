"""Tests for the route cache. They use Django's in-memory cache instead of Redis,
so they don't need Redis running and never touch the real cached routes."""

from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from redis.exceptions import RedisError

from route_planner.services.location_resolver import Place
from route_planner.services.route_cache import CachedRoutingClient
from route_planner.services.routing_api import NoRouteFound, Route

CHICAGO = Place("Chicago, IL", 41.837551, -87.681844)
ST_LOUIS = Place("St. Louis, MO", 38.635699, -90.244582)
A_ROUTE = Route(points=[(41.84, -87.68), (38.64, -90.24)], distance_miles=305.7, duration_hours=4.7)


class CountingRoutingClient:
    """A fake routing client that counts how often it's called (each call = one real API call)."""

    PROFILE = "driving-car"

    def __init__(self, error: Exception | None = None):
        self.calls = 0
        self.error = error

    def get_route(self, start: Place, finish: Place) -> Route:
        self.calls += 1
        if self.error:
            raise self.error
        return A_ROUTE


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class CachedRoutingClientTests(SimpleTestCase):
    def setUp(self):
        cache.clear()  # every test starts with an empty cache
        self.routing_api = CountingRoutingClient()
        self.cached_client = CachedRoutingClient(self.routing_api)

    def test_repeat_trip_uses_the_cache(self):
        first = self.cached_client.get_route(CHICAGO, ST_LOUIS)
        repeat = self.cached_client.get_route(CHICAGO, ST_LOUIS)

        self.assertEqual(self.routing_api.calls, 1)
        self.assertEqual(repeat, first)

    def test_same_place_typed_differently_shares_one_entry(self):
        chicago_lowercase = Place("chicago, illinois", CHICAGO.latitude, CHICAGO.longitude)

        self.cached_client.get_route(CHICAGO, ST_LOUIS)
        self.cached_client.get_route(chicago_lowercase, ST_LOUIS)

        self.assertEqual(self.routing_api.calls, 1)

    def test_each_direction_is_cached_separately(self):
        self.cached_client.get_route(CHICAGO, ST_LOUIS)
        self.cached_client.get_route(ST_LOUIS, CHICAGO)

        self.assertEqual(self.routing_api.calls, 2)

    def test_errors_are_not_cached(self):
        failing_api = CountingRoutingClient(error=NoRouteFound("No driving route was found."))
        cached_client = CachedRoutingClient(failing_api)

        for _ in range(2):
            with self.assertRaises(NoRouteFound):
                cached_client.get_route(CHICAGO, ST_LOUIS)

        self.assertEqual(failing_api.calls, 2)  # the API was asked both times

    def test_still_works_when_redis_is_down(self):
        with mock.patch("route_planner.services.route_cache.cache") as broken_cache:
            broken_cache.get.side_effect = RedisError("Connection refused")
            broken_cache.set.side_effect = RedisError("Connection refused")

            with self.assertLogs("route_planner.services.route_cache", level="WARNING"):
                route = self.cached_client.get_route(CHICAGO, ST_LOUIS)

        self.assertEqual(route, A_ROUTE)  # the trip is still planned, straight from the API
        self.assertEqual(self.routing_api.calls, 1)