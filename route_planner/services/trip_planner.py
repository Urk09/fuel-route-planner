"""Plans a whole trip: place → route → stations near the road → fuel plan."""

from dataclasses import dataclass

from route_planner.models import FuelStation
from route_planner.services.route_cache import CachedRoutingClient
from route_planner.services.location_resolver import LocationResolver, Place
from route_planner.services.optimizer import FuelOption, FuelPlan, FuelPlanner, PlannedStop
from route_planner.services.routing_api import OpenRouteServiceClient, Route
from route_planner.services.stations_on_route import StationFinder, StationOnRoute


@dataclass(frozen=True)
class TripStop:
    """One fuel stop, with everything the API shows about it."""

    station: FuelStation  # name, address, city, state
    purchase: PlannedStop  # mile, price, gallons, cost
    on_route: StationOnRoute  # off_route_miles, route_point


@dataclass(frozen=True)
class TripPlan:
    """The whole answer for one trip."""

    start: Place
    finish: Place
    route: Route
    fuel_planner: FuelPlanner
    skip_small_stops: bool
    stops: list[TripStop]
    total_gallons: float
    total_cost: float
    notes: list[str]


class TripPlanner:
    """Runs every step for one trip. The API view calls `plan()`.

    Each helper is a setting with a sensible default, so a test can pass a fake one
    (for example a routing client that never calls the real API).
    Errors from each step are passed up to the view, which turns them into HTTP errors.
    """

    def __init__(
        self,
        location_resolver: LocationResolver | None = None,
        routing_client: CachedRoutingClient | OpenRouteServiceClient | None = None,
        station_finder: StationFinder | None = None,
        fuel_planner: FuelPlanner | None = None,
    ):
        self.location_resolver = location_resolver or LocationResolver()
        self.routing_client = routing_client or CachedRoutingClient()  # Redis first, then OpenRouteService
        self.station_finder = station_finder or StationFinder()
        self.fuel_planner = fuel_planner or FuelPlanner()  # the vehicle: the brief's car by default

    def plan(self, start_text: str, finish_text: str, skip_small_stops: bool = False) -> TripPlan:
        """Text in, full plan out. `skip_small_stops` avoids stops that would buy only a little fuel."""
        fuel_planner = self.fuel_planner.skipping_small_stops() if skip_small_stops else self.fuel_planner

        start = self.location_resolver.resolve(start_text)
        finish = self.location_resolver.resolve(finish_text)
        route = self.routing_client.get_route(start, finish)

        stations_on_route = self.station_finder.find_near_route(route, FuelStation.objects.all())
        fuel_options = self._fuel_options(stations_on_route)
        fuel_plan = fuel_planner.plan(fuel_options, route.distance_miles)

        return TripPlan(
            start=start,
            finish=finish,
            route=route,
            fuel_planner=fuel_planner,
            skip_small_stops=skip_small_stops,
            stops=self._trip_stops(fuel_plan, stations_on_route),
            total_gallons=fuel_plan.total_gallons,
            total_cost=fuel_plan.total_cost,
            notes=fuel_plan.notes,
        )

    @staticmethod
    def _fuel_options(stations_on_route: list[StationOnRoute]) -> list[FuelOption]:
        """What the optimizer needs from each station: where it is on the trip and its price."""
        return [
            FuelOption(
                mile=item.mile_marker,
                price=float(item.station.retail_price),
                station_id=item.station.id,
            )
            for item in stations_on_route
        ]

    @staticmethod
    def _trip_stops(fuel_plan: FuelPlan, stations_on_route: list[StationOnRoute]) -> list[TripStop]:
        """Join each purchase with its station's details."""
        on_route_by_station_id = {item.station.id: item for item in stations_on_route}
        stops = []
        for purchase in fuel_plan.stops:
            on_route = on_route_by_station_id[purchase.station_id]
            stops.append(TripStop(station=on_route.station, purchase=purchase, on_route=on_route))
        return stops