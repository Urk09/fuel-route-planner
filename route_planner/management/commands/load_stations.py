"""Loads the fuel price CSV into the FuelStation table. Safe to re-run: existing stations are updated."""

import csv
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from route_planner.models import FuelStation
from route_planner.services.city_lookup import CityLookup
from route_planner.services.us_states import US_STATES


class Command(BaseCommand):
    help = "Load fuel stations from the OPIS price CSV into the database."

    PRICES_FILE = Path(settings.BASE_DIR) / "data" / "fuel-prices-for-be-assessment.csv"
    FIELDS_TO_UPDATE = [
        "name", "address", "city", "state", "rack_id",
        "retail_price", "latitude", "longitude", "updated_at",
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Read and clean the CSV and print the counts, but save nothing.",
        )

    def handle(self, *args, **options):
        stations = self._read_stations()
        to_save = self._attach_coordinates(stations)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: nothing was saved."))
            return

        self._save(to_save)

    def _read_stations(self) -> dict[int, dict]:
        """Read the CSV: US rows only, one entry per station, keeping its lowest price."""
        stations = {}
        rows_read = 0
        rows_skipped = 0

        with open(self.PRICES_FILE, newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                rows_read += 1

                state = self.clean_text(row["State"]).upper()
                if state not in US_STATES:
                    rows_skipped += 1
                    continue

                opis_id = int(row["OPIS Truckstop ID"])
                price = Decimal(row["Retail Price"]).quantize(Decimal("0.001"))

                if opis_id not in stations or price < stations[opis_id]["retail_price"]:
                    stations[opis_id] = {
                        "opis_id": opis_id,
                        "name": self.clean_text(row["Truckstop Name"]),
                        "address": self.clean_text(row["Address"]),
                        "city": self.clean_text(row["City"]),
                        "state": state,
                        "rack_id": int(row["Rack ID"]),
                        "retail_price": price,
                    }

        self.stdout.write(f"Rows read:             {rows_read}")
        self.stdout.write(f"Rows skipped (not US): {rows_skipped}")
        self.stdout.write(f"Unique US stations:    {len(stations)}")
        return stations

    def _attach_coordinates(self, stations: dict[int, dict]) -> list[FuelStation]:
        """Place each station at its city's location. Stations whose city isn't found are left out."""
        city_lookup = CityLookup()
        to_save = []
        not_found = set()

        for station in stations.values():
            coordinates = city_lookup.find(station["city"], station["state"])
            if coordinates is None:
                not_found.add((station["city"], station["state"]))
                continue
            latitude, longitude = coordinates
            to_save.append(FuelStation(**station, latitude=latitude, longitude=longitude))

        self.stdout.write(f"Stations located:      {len(to_save)}")
        if not_found:
            self.stdout.write(self.style.WARNING(f"Cities not found ({len(not_found)}): {sorted(not_found)}"))
        return to_save

    def _save(self, to_save: list[FuelStation]) -> None:
        """Insert new stations and update existing ones (matched by OPIS ID), 1,000 rows at a time."""
        FuelStation.objects.bulk_create(
            to_save,
            batch_size=1000,
            update_conflicts=True,
            unique_fields=["opis_id"],
            update_fields=self.FIELDS_TO_UPDATE,
        )
        self.stdout.write(self.style.SUCCESS(f"Saved {len(to_save)} stations."))

    @staticmethod
    def clean_text(value: str) -> str:
        """Trim the ends and collapse inner spaces: '  I-35,  EXIT 271 ' -> 'I-35, EXIT 271'."""
        return " ".join(value.split())