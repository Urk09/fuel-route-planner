from django.urls import path

from route_planner.views import TripPlanView

urlpatterns = [
    path("trip-plan/", TripPlanView.as_view(), name="trip-plan"),
]