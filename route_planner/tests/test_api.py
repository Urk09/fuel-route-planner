"""Tests for the API endpoint. A fake routing client stands in for OpenRouteService:
no network, no API key, no quota used."""

from decimal import Decimal
from unittest import mock

from django.urls import reverse
from rest_framework.test import APITestCase

from route_planner.models import FuelStation
from route_planner.services.routing_api import NoRouteFound, Route, RoutingError
from route_planner.services.stations_on_route import StationFinder
from route_planner.services.trip_planner import TripPlanner
from route_planner.views import TripPlanView

# A straight road going south: 301 points, 0.01° of latitude apart (about 0.7 miles).
ROAD_POINTS = [(41.0 - index * 0.01, -89.0) for index in range(301)]
ROAD_MILES = StationFinder.mile_markers(ROAD_POINTS)[-1]  # about 207 miles


class FakeRoutingClient:
    """Stands in for OpenRouteService: returns the straight road above, or raises the error it's given."""

    def __init__(self, distance_miles: float = ROAD_MILES, error: Exception | None = None):
        self.distance_miles = distance_miles
        self.error = error

    def get_route(self, start, finish) -> Route:
        if self.error:
            raise self.error
        return Route(points=ROAD_POINTS, distance_miles=self.distance_miles, duration_hours=3.0)


class TripPlanApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Runs once for the whole class: three stations, saved in the test database.
        cls.create_station(1, "START STOP", price="3.500", latitude=41.0, longitude=-89.0)  # at the start
        cls.create_station(2, "CHEAP STOP", price="3.000", latitude=40.0, longitude=-89.0)  # ~69 miles in
        cls.create_station(3, "FAR AWAY STOP", price="1.000", latitude=45.0, longitude=-80.0)  # nowhere near

    @staticmethod
    def create_station(opis_id: int, name: str, price: str, latitude: float, longitude: float) -> None:
        FuelStation.objects.create(
            opis_id=opis_id,
            name=name,
            address=f"I-39, EXIT {opis_id}",
            city="Test City",
            state="IL",
            rack_id=1,
            retail_price=Decimal(price),
            latitude=latitude,
            longitude=longitude,
        )

    def plan(self, body: dict, routing_client: FakeRoutingClient | None = None):
        """POST to the endpoint, with the view's planner using a fake routing client for this call only."""
        planner = TripPlanner(routing_client=routing_client or FakeRoutingClient())
        with mock.patch.object(TripPlanView, "trip_planner", planner):
            return self.client.post(reverse("trip-plan"), body, format="json")

    def test_plans_a_trip_with_the_cheapest_stops(self):
        response = self.plan({"start": "Chicago, IL", "finish": "St. Louis, MO"})

        self.assertEqual(response.status_code, 200)
        stops = response.json()["fuel_stops"]
        # Buy just enough at the start to reach the cheaper station, then the rest there.
        # The far-away station (the cheapest of all) is ignored: it's not near the road.
        self.assertEqual([stop["name"] for stop in stops], ["START STOP", "CHEAP STOP"])
        self.assertEqual(stops[0]["location_precision"], "city")

    def test_numbers_add_up(self):
        data = self.plan({"start": "Chicago, IL", "finish": "St. Louis, MO"}).json()

        stop_costs = sum(Decimal(stop["cost"]) for stop in data["fuel_stops"])
        self.assertEqual(Decimal(data["total_fuel_cost"]), stop_costs)
        self.assertAlmostEqual(float(data["total_gallons"]), data["distance_miles"] / 10, places=1)

    def test_missing_field_returns_400(self):
        response = self.plan({"start": "Chicago, IL"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("finish", response.json())

    def test_unknown_city_returns_422(self):
        response = self.plan({"start": "Nowhere, IL", "finish": "St. Louis, MO"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("not found", response.json()["detail"])

    def test_impossible_trip_returns_422(self):
        # A 900-mile trip, but the last station is at mile ~69: nowhere to refuel after that.
        response = self.plan(
            {"start": "Chicago, IL", "finish": "St. Louis, MO"},
            routing_client=FakeRoutingClient(distance_miles=900),
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("No fuel station within 500 miles", response.json()["detail"])

    def test_no_road_returns_422(self):
        response = self.plan(
            {"start": "Chicago, IL", "finish": "St. Louis, MO"},
            routing_client=FakeRoutingClient(error=NoRouteFound("No driving route was found.")),
        )

        self.assertEqual(response.status_code, 422)

    def test_routing_service_down_returns_503(self):
        with self.assertLogs("route_planner.views", level="WARNING"):
            response = self.plan(
                {"start": "Chicago, IL", "finish": "St. Louis, MO"},
                routing_client=FakeRoutingClient(error=RoutingError("Could not reach the routing service.")),
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Could not reach the routing service.")