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
    start = PlaceSerializer()
    finish = PlaceSerializer()
    distance_miles = RoundedFloatField(1, source="route.distance_miles")
    duration_hours = RoundedFloatField(1, source="route.duration_hours")
    vehicle = VehicleSerializer(source="fuel_planner")
    fuel_stops = TripStopSerializer(source="stops", many=True)
    total_gallons = RoundedDecimalField(2)
    total_fuel_cost = serializers.SerializerMethodField()
    notes = serializers.ListField(child=serializers.CharField())
    route = serializers.SerializerMethodField()

    def get_total_fuel_cost(self, plan) -> str:
        # Add up the rounded stop costs, so the numbers on screen always add up.
        rounded_costs = [RoundedDecimalField.round(stop.purchase.cost, 2) for stop in plan.stops]
        return str(sum(rounded_costs, Decimal("0.00")))

    def get_route(self, plan) -> dict:
        # The road as GeoJSON, the standard map format. GeoJSON order is [longitude, latitude].
        coordinates = [
            [round(longitude, COORDINATE_DECIMALS), round(latitude, COORDINATE_DECIMALS)]
            for latitude, longitude in plan.route.points
        ]
        return {"type": "LineString", "coordinates": coordinates}