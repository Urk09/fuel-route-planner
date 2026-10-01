"""Tests for the fuel algorithm. No database needed, so these use SimpleTestCase."""

from django.test import SimpleTestCase

from route_planner.services.optimizer import FuelOption, FuelPlanError, FuelPlanner


def stops_summary(plan):
    """Each stop as (mile, gallons), rounded so the numbers are easy to compare."""
    return [(stop.mile, round(stop.gallons, 2)) for stop in plan.stops]


class FuelPlannerTests(SimpleTestCase):
    def setUp(self):
        # Runs before every test: a fresh planner with the brief's car (500 miles, 10 mpg).
        self.planner = FuelPlanner()

    def test_buys_just_enough_to_reach_cheaper_fuel(self):
        fuel_options = [
            FuelOption(mile=0, price=3.50, station_id=1),
            FuelOption(mile=200, price=3.10, station_id=2),
            FuelOption(mile=450, price=3.40, station_id=3),
            FuelOption(mile=600, price=2.90, station_id=4),
            FuelOption(mile=900, price=3.30, station_id=5),
        ]
        plan = self.planner.plan(fuel_options, trip_miles=1000)

        self.assertEqual(stops_summary(plan), [(0, 20), (200, 40), (600, 40)])
        self.assertAlmostEqual(plan.total_cost, 310.00)

    def test_fills_up_when_nothing_cheaper_is_within_reach(self):
        fuel_options = [
            FuelOption(mile=0, price=3.00, station_id=1),
            FuelOption(mile=300, price=3.40, station_id=2),
            FuelOption(mile=650, price=3.20, station_id=3),
        ]
        plan = self.planner.plan(fuel_options, trip_miles=1000)

        self.assertEqual(stops_summary(plan), [(0, 50), (300, 15), (650, 35)])
        self.assertAlmostEqual(plan.total_cost, 313.00)

    def test_short_trip_needs_only_one_stop(self):
        fuel_options = [
            FuelOption(mile=0, price=3.00, station_id=1),
            FuelOption(mile=150, price=3.20, station_id=2),
        ]
        plan = self.planner.plan(fuel_options, trip_miles=300)

        self.assertEqual(stops_summary(plan), [(0, 30)])

    def test_keeps_only_the_cheapest_station_at_the_same_spot(self):
        fuel_options = [
            FuelOption(mile=0, price=3.60, station_id=1),
            FuelOption(mile=0, price=3.40, station_id=2),
            FuelOption(mile=0, price=3.50, station_id=3),
        ]
        plan = self.planner.plan(fuel_options, trip_miles=200)

        self.assertEqual([stop.station_id for stop in plan.stops], [2])

    def test_a_gap_of_exactly_500_miles_is_fine(self):
        fuel_options = [
            FuelOption(mile=0, price=3.00, station_id=1),
            FuelOption(mile=500, price=3.00, station_id=2),
        ]
        plan = self.planner.plan(fuel_options, trip_miles=1000)

        self.assertEqual(stops_summary(plan), [(0, 50), (500, 50)])

    def test_a_gap_over_500_miles_is_impossible(self):
        fuel_options = [
            FuelOption(mile=0, price=3.00, station_id=1),
            FuelOption(mile=501, price=3.00, station_id=2),
        ]
        with self.assertRaisesMessage(FuelPlanError, "between mile 0 and mile 501"):
            self.planner.plan(fuel_options, trip_miles=1000)

    def test_no_station_at_the_start_assumes_a_full_tank(self):
        fuel_options = [FuelOption(mile=300, price=3.00, station_id=1)]
        plan = self.planner.plan(fuel_options, trip_miles=600)

        # Full tank at the start (500 miles). At mile 300, 200 miles are left in the tank;
        # the last 300 miles need 100 more = 10 gallons.
        self.assertEqual(stops_summary(plan), [(300, 10)])
        self.assertIn("assumed a full tank", plan.notes[0])

    def test_total_gallons_equal_distance_divided_by_mpg(self):
        fuel_options = [
            FuelOption(mile=0, price=3.10, station_id=1),
            FuelOption(mile=180, price=3.30, station_id=2),
            FuelOption(mile=420, price=2.95, station_id=3),
            FuelOption(mile=760, price=3.05, station_id=4),
        ]
        plan = self.planner.plan(fuel_options, trip_miles=1150)

        self.assertAlmostEqual(plan.total_gallons, 1150 / 10)

    def test_vehicle_settings_change_the_plan(self):
        fuel_options = [
            FuelOption(mile=0, price=3.00, station_id=1),
            FuelOption(mile=150, price=3.20, station_id=2),
        ]
        small_tank_vehicle = FuelPlanner(range_miles=200, miles_per_gallon=5)
        plan = small_tank_vehicle.plan(fuel_options, trip_miles=300)

        # Can't reach the finish on one tank: fill up (40 gallons), then top up at mile 150.
        self.assertEqual(stops_summary(plan), [(0, 40), (150, 20)])

    def test_skip_small_stops_drives_past_a_stop_that_would_buy_only_a_little(self):
        fuel_options = [
            FuelOption(mile=0, price=3.40, station_id=1),
            FuelOption(mile=200, price=3.30, station_id=2),
            FuelOption(mile=201, price=3.00, station_id=3),
        ]

        cheapest = self.planner.plan(fuel_options, trip_miles=400)
        without_small_stops = self.planner.skipping_small_stops().plan(fuel_options, trip_miles=400)

        # The cheapest plan stops at mile 200 for 0.1 gallons; with the option on, we drive past it.
        self.assertEqual(stops_summary(cheapest), [(0, 20), (200, 0.1), (201, 19.9)])
        self.assertEqual(stops_summary(without_small_stops), [(0, 20.1), (201, 19.9)])

    def test_skip_small_stops_keeps_a_small_stop_the_trip_needs(self):
        fuel_options = [
            FuelOption(mile=0, price=3.00, station_id=1),
            FuelOption(mile=450, price=3.50, station_id=2),
        ]
        plan = self.planner.skipping_small_stops().plan(fuel_options, trip_miles=520)

        # Only 2 gallons at mile 450, but without it the car can't reach the finish.
        self.assertEqual(stops_summary(plan), [(0, 50), (450, 2)])