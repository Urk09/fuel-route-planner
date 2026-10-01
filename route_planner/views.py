"""The API endpoint. It only handles HTTP: read the request, call the planner, send the answer."""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from route_planner.serializers import TripPlanSerializer, TripRequestSerializer
from route_planner.services.location_resolver import LocationError
from route_planner.services.optimizer import FuelPlanError
from route_planner.services.routing_api import NoRouteFound, RoutingError
from route_planner.services.trip_planner import TripPlanner

logger = logging.getLogger(__name__)


class TripPlanView(APIView):
    """POST /api/v1/trip-plan/  with a JSON body: {"start": "Chicago, IL", "finish": "St. Louis, MO"}

    Optional: "skip_small_stops": true, to avoid stops that would buy only a little fuel.
    """

    # One shared planner for every request. It keeps no data between requests, so sharing is safe.
    trip_planner = TripPlanner()

    def post(self, request):
        trip_request = TripRequestSerializer(data=request.data)
        trip_request.is_valid(raise_exception=True)  # missing or empty field -> 400 with the details

        try:
            trip = self.trip_planner.plan(
                trip_request.validated_data["start"],
                trip_request.validated_data["finish"],
                skip_small_stops=trip_request.validated_data["skip_small_stops"],
            )
        except (LocationError, NoRouteFound, FuelPlanError) as error:
            # The request was fine, but this trip can't be planned: the caller can change it.
            return Response({"detail": str(error)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except RoutingError as error:
            # The routing service is down, slow or out of quota: not the caller's fault.
            logger.warning("Routing service problem: %s", error)
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(TripPlanSerializer(trip).data)