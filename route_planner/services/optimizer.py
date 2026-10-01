"""The fuel algorithm: where to stop and how much to buy"""

from dataclasses import dataclass, replace

DEFAULT_RANGE_MILES = 500.0
DEFAULT_MILES_PER_GALLON = 10.0
SMALL_STOP_SHARE_OF_TANK = 0.10  # with "skip small stops", a stop must buy at least 10% of a tank
START_AREA_MILES = 10.0
MIN_GALLONS = 0.001


class FuelPlanError(Exception):
    """No plan is possible: a gap longer than the vehicle's range."""


@dataclass(frozen=True)
class FuelOption:
    """A place to buy fuel: where it is on the trip and what it costs."""

    mile: float
    price: float
    station_id: int | None


@dataclass(frozen=True)
class PlannedStop:
    """One purchase in the plan."""

    station_id: int
    mile: float
    price: float
    gallons: float
    cost: float


@dataclass(frozen=True)
class FuelPlan:
    """The answer: every purchase, plus the totals."""

    stops: list[PlannedStop]
    total_gallons: float
    total_cost: float
    notes: list[str]


class FuelPlanner:
    """
    Plans the cheapest fuel stops for one vehicle.
    Fuel in the tank is tracked in miles of driving, not gallons.
    """

    def __init__(
        self,
        range_miles: float = DEFAULT_RANGE_MILES,
        miles_per_gallon: float = DEFAULT_MILES_PER_GALLON,
        min_purchase_gallons: float = 0.0,
    ):
        self.range_miles = range_miles
        self.miles_per_gallon = miles_per_gallon
        self.min_purchase_gallons = min_purchase_gallons  # 0 = off: the plan is cheapest to the cent

    def skipping_small_stops(self) -> "FuelPlanner":
        """The same vehicle, but every stop must buy at least 10% of a tank (5 gallons for the brief's car)."""
        
        tank_gallons = self.range_miles / self.miles_per_gallon
        return FuelPlanner(
            range_miles=self.range_miles,
            miles_per_gallon=self.miles_per_gallon,
            min_purchase_gallons=tank_gallons * SMALL_STOP_SHARE_OF_TANK,
        )

    def plan(self, fuel_options: list[FuelOption], trip_miles: float) -> FuelPlan:
        """The cheapest plan, then (if a minimum purchase is set) without small stops.

        Plan, find a stop that buys too little, drop that station, plan again.
        A small stop is kept when the trip is impossible without it.
        """
        fuel_options = list(fuel_options)
        plan = self._cheapest_plan(fuel_options, trip_miles)
        stations_to_keep: set[int] = set()

        while True:
            small_stop = self._first_small_stop(plan, stations_to_keep)
            if small_stop is None:
                return plan

            options_without_stop = [
                option for option in fuel_options if option.station_id != small_stop.station_id
            ]
            try:
                plan = self._cheapest_plan(options_without_stop, trip_miles)
                fuel_options = options_without_stop
            except FuelPlanError:
                stations_to_keep.add(small_stop.station_id)

    def _first_small_stop(self, plan: FuelPlan, stations_to_keep: set[int]) -> PlannedStop | None:
        """The first stop that buys less than the minimum. The first fill-up doesn't count:
        the tank starts empty, so that purchase can't be skipped."""
        for stop in plan.stops:
            is_first_fill_up = stop.mile == 0
            if (
                stop.gallons < self.min_purchase_gallons
                and not is_first_fill_up
                and stop.station_id not in stations_to_keep
            ):
                return stop
        return None

    def _cheapest_plan(self, fuel_options: list[FuelOption], trip_miles: float) -> FuelPlan:
        """The cheapest way to buy fuel for a trip of `trip_miles`"""
        
        stations, miles_in_tank, notes = self._starting_point(self._cheapest_per_spot(fuel_options))
        planned_stops: list[PlannedStop] = []
        current_station = stations[0]

        while True:
            farthest_reachable_mile = current_station.mile + self.range_miles
            reachable_stations = [
                station
                for station in stations
                if current_station.mile < station.mile <= farthest_reachable_mile
            ]

            # cheaper fuel within reach -> buy just enough to get to the first one.
            first_cheaper_station = next(
                (station for station in reachable_stations if station.price < current_station.price),
                None,
            )
            if first_cheaper_station is not None:
                miles_to_drive = first_cheaper_station.mile - current_station.mile
                miles_in_tank = self._buy_fuel(planned_stops, current_station, miles_in_tank, miles_to_drive)
                miles_in_tank -= miles_to_drive
                current_station = first_cheaper_station
                continue

            # the finish is within reach -> buy just enough to get there.
            miles_to_finish = trip_miles - current_station.mile
            if miles_to_finish <= self.range_miles:
                self._buy_fuel(planned_stops, current_station, miles_in_tank, miles_to_finish)
                break

            # no station within reach -> the trip is impossible.
            if not reachable_stations:
                next_station_mile = next(
                    (station.mile for station in stations if station.mile > current_station.mile),
                    trip_miles,
                )
                raise FuelPlanError(
                    f"No fuel station within {self.range_miles:.0f} miles between mile "
                    f"{current_station.mile:.0f} and mile {next_station_mile:.0f} of this route."
                )

            # fill the tank, then go to the cheapest station within reach.
            cheapest_reachable_station = min(
                reachable_stations, key=lambda station: (station.price, -station.mile)
            )
            miles_to_drive = cheapest_reachable_station.mile - current_station.mile
            miles_in_tank = self._buy_fuel(planned_stops, current_station, miles_in_tank, self.range_miles)
            miles_in_tank -= miles_to_drive
            current_station = cheapest_reachable_station

        total_gallons = sum(stop.gallons for stop in planned_stops)
        total_cost = sum(stop.cost for stop in planned_stops)
        return FuelPlan(planned_stops, total_gallons, total_cost, notes)

    @staticmethod
    def _cheapest_per_spot(fuel_options: list[FuelOption]) -> list[FuelOption]:
        """Several stations at the same mile: keep only the cheapest. Sorted by mile."""
        
        cheapest_at_mile: dict[float, FuelOption] = {}
        
        for option in fuel_options:
            if option.mile not in cheapest_at_mile or option.price < cheapest_at_mile[option.mile].price:
                cheapest_at_mile[option.mile] = option
        
        return sorted(cheapest_at_mile.values(), key=lambda option: option.mile)

    def _starting_point(self, stations: list[FuelOption]) -> tuple[list[FuelOption], float, list[str]]:
        """Where the trip starts, and how many miles of fuel are in the tank."""
        
        stations_near_start = [station for station in stations if station.mile <= START_AREA_MILES]
        stations_after_start = [station for station in stations if station.mile > START_AREA_MILES]

        if stations_near_start:
            
            cheapest_near_start = min(stations_near_start, key=lambda station: station.price) # Empty tank: fill up at the cheapest station near the start.
            
            return [replace(cheapest_near_start, mile=0.0)] + stations_after_start, 0.0, []

        # Fallback: nowhere to buy at the start, so assume a full tank (not counted in the total).
        note = (
            "No fuel station near the start in the price data; "
            "assumed a full tank at departure (not included in the total)."
        )
        
        start_without_station = FuelOption(mile=0.0, price=float("inf"), station_id=None)
        
        return [start_without_station] + stations_after_start, self.range_miles, [note]

    def _buy_fuel(
        self,
        planned_stops: list[PlannedStop],
        station: FuelOption,
        miles_in_tank: float,
        target_miles: float,
    ) -> float:
        """Buy at `station` until the tank holds `target_miles`.

        Adds the purchase to `planned_stops` and returns the new miles in the tank.
        """
        miles_to_add = target_miles - miles_in_tank
        if miles_to_add <= 0 or station.station_id is None:
            return miles_in_tank

        gallons_to_buy = miles_to_add / self.miles_per_gallon
        
        if gallons_to_buy >= MIN_GALLONS:
            planned_stops.append(
                PlannedStop(
                    station_id=station.station_id,
                    mile=station.mile,
                    price=station.price,
                    gallons=gallons_to_buy,
                    cost=gallons_to_buy * station.price,
                )
            )
        
        return target_miles