"""Shapes the API's input and output.

Money and gallons are sent as text ("94.56") so they stay exact; JSON numbers are floats.
"""

from decimal import ROUND_HALF_UP, Decimal

from rest_framework import serializers

COORDINATE_DECIMALS = 5


class RoundedDecimalField(serializers.Field):
    """A number sent as exact text, e.g. 94.5649 -> "94.56". Used for money, prices and gallons."""

    def __init__(self, decimal_places: int, **kwargs):
        self.decimal_places = decimal_places
        super().__init__(read_only=True, **kwargs)

    def to_representation(self, value) -> str:
        return str(self.round(value, self.decimal_places))

    @staticmethod
    def round(value, decimal_places: int) -> Decimal:
        step = Decimal(10) ** -decimal_places  # 2 -> Decimal("0.01")
        return Decimal(str(value)).quantize(step, rounding=ROUND_HALF_UP)


class RoundedFloatField(serializers.Field):
    """A plain number, rounded so it's easy to read, e.g. 305.6873 -> 305.7."""

    def __init__(self, decimal_places: int, **kwargs):
        self.decimal_places = decimal_places
        super().__init__(read_only=True, **kwargs)

    def to_representation(self, value) -> float:
        return round(float(value), self.decimal_places)


class TripRequestSerializer(serializers.Serializer):
    """Checks the input: both places are required."""

    start = serializers.CharField(max_length=200)
    finish = serializers.CharField(max_length=200)
    skip_small_stops = serializers.BooleanField(required=False, default=False)


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField()
    latitude = RoundedFloatField(COORDINATE_DECIMALS)
    longitude = RoundedFloatField(COORDINATE_DECIMALS)


class VehicleSerializer(serializers.Serializer):
    range_miles = serializers.FloatField()
    miles_per_gallon = serializers.FloatField()


class TripStopSerializer(serializers.Serializer):
    station_id = serializers.IntegerField(source="station.id")
    name = serializers.CharField(source="station.name")
    address = serializers.CharField(source="station.address")
    city = serializers.CharField(source="station.city")
    state = serializers.CharField(source="station.state")
    mile = RoundedFloatField(1, source="purchase.mile")
    price_per_gallon = RoundedDecimalField(3, source="station.retail_price")
    gallons = RoundedDecimalField(2, source="purchase.gallons")
    cost = RoundedDecimalField(2, source="purchase.cost")
    off_route_miles = RoundedFloatField(1, source="on_route.off_route_miles")
    location_precision = serializers.SerializerMethodField()
    route_point = serializers.SerializerMethodField()

    def get_location_precision(self, stop) -> str:
        # Every station is placed at its city's location (see the README).
        return "city"

    def get_route_point(self, stop) -> dict:
        # The point on the road next to the station: where the map draws the marker.
        latitude, longitude = stop.on_route.route_point
        return {
            "latitude": round(latitude, COORDINATE_DECIMALS),
            "longitude": round(longitude, COORDINATE_DECIMALS),
        }


class TripPlanSerializer(serializers.Serializer):

    ROAD_COLOR = "#2563eb"
    START_COLOR = "#16a34a"
    FINISH_COLOR = "#dc2626"
    FUEL_STOP_COLOR = "#f59e0b"

    start = PlaceSerializer()
    finish = PlaceSerializer()
    distance_miles = RoundedFloatField(1, source="route.distance_miles")
    duration_hours = RoundedFloatField(1, source="route.duration_hours")
    vehicle = VehicleSerializer(source="fuel_planner")
    skip_small_stops = serializers.BooleanField()
    fuel_stops = TripStopSerializer(source="stops", many=True)
    total_gallons = RoundedDecimalField(2)
    total_fuel_cost = serializers.SerializerMethodField()
    notes = serializers.ListField(child=serializers.CharField())
    map = serializers.SerializerMethodField()

    def get_total_fuel_cost(self, plan) -> str:
        # Add up the rounded stop costs, so the numbers on screen always add up.
        rounded_costs = [RoundedDecimalField.round(stop.purchase.cost, 2) for stop in plan.stops]
        return str(sum(rounded_costs, Decimal("0.00")))

    def get_map(self, plan) -> dict:
        """The whole trip as GeoJSON, the standard map format: the road, the start, the finish
        and every fuel stop with its details. Paste it into geojson.io to see it."""
        features = [
            self._road(plan.route.points),
            self._marker(
                plan.start.latitude,
                plan.start.longitude,
                {"kind": "start", "label": plan.start.label, "marker-color": self.START_COLOR},
            ),
            self._marker(
                plan.finish.latitude,
                plan.finish.longitude,
                {"kind": "finish", "label": plan.finish.label, "marker-color": self.FINISH_COLOR},
            ),
        ]
        for stop_number, stop in enumerate(plan.stops, start=1):
            details = dict(TripStopSerializer(stop).data)  # name, price, gallons, cost, ...
            details.pop("route_point")  # already the marker's position
            latitude, longitude = stop.on_route.route_point
            features.append(
                self._marker(
                    latitude,
                    longitude,
                    {"kind": "fuel_stop", "stop_number": stop_number, **details, "marker-color": self.FUEL_STOP_COLOR},
                )
            )
        return {"type": "FeatureCollection", "features": features}

    def _road(self, points: list[tuple[float, float]]) -> dict:
        """The road as a line. GeoJSON order is [longitude, latitude]."""
        coordinates = [self._coordinates(latitude, longitude) for latitude, longitude in points]
        return {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "properties": {"kind": "road", "stroke": self.ROAD_COLOR, "stroke-width": 4},
        }

    def _marker(self, latitude: float, longitude: float, properties: dict) -> dict:
        """One point on the map, with the details shown when you click it."""
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": self._coordinates(latitude, longitude)},
            "properties": properties,
        }

    @staticmethod
    def _coordinates(latitude: float, longitude: float) -> list[float]:
        """[longitude, latitude], rounded to 5 decimals (about 1 metre)."""
        return [round(longitude, COORDINATE_DECIMALS), round(latitude, COORDINATE_DECIMALS)]