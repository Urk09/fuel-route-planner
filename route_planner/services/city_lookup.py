"""Finds a US city's coordinates offline, from the free city list plus our hand-checked fixes."""

import csv
from functools import cache
from pathlib import Path

from django.conf import settings


class CityLookup:
    """(city, state) -> (latitude, longitude). The files are read once, on first use."""

    CITIES_FILE = Path(settings.BASE_DIR) / "data" / "us_cities.csv"
    OVERRIDES_FILE = Path(settings.BASE_DIR) / "data" / "city_overrides.csv"
    ABBREVIATIONS = {"st": "saint", "ste": "sainte", "ft": "fort", "mt": "mount"}

    def find(self, city: str, state: str) -> tuple[float, float] | None:
        """Coordinates for the city, or None if it isn't in the list."""
        key = (state.strip().upper(), self.normalize_city(city))
        return self._load_cities().get(key)

    @classmethod
    def normalize_city(cls, name: str) -> str:
        """"St. Louis" and "Saint Louis" -> "saint louis", so both spellings match."""
        name = name.lower().replace(".", " ")
        words = [cls.ABBREVIATIONS.get(word, word) for word in name.split()]
        return " ".join(words)

    @classmethod
    @cache
    def _load_cities(cls) -> dict[tuple[str, str], tuple[float, float]]:
        """Read both files. `@cache` keeps the result, so later calls don't read them again."""
        cities: dict[tuple[str, str], tuple[float, float]] = {}

        with open(cls.CITIES_FILE, newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                key = (row["STATE_CODE"], cls.normalize_city(row["CITY"]))
                # Some cities have several rows (one per county): keep the first.
                if key not in cities:
                    cities[key] = (float(row["LATITUDE"]), float(row["LONGITUDE"]))

        with open(cls.OVERRIDES_FILE, newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                # Hand-checked fixes always replace the city list's entry.
                key = (row["state"].strip().upper(), cls.normalize_city(row["city"]))
                cities[key] = (float(row["latitude"]), float(row["longitude"]))

        return cities