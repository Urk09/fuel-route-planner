import csv
from functools import cache
from pathlib import Path

from django.conf import settings

CITIES_FILE = Path(settings.BASE_DIR) / "data" / "us_cities.csv"
OVERRIDES_FILE = Path(settings.BASE_DIR) / "data" / "city_overrides.csv"

ABBREVIATIONS = {"st": "saint", "ste": "sainte", "ft": "fort", "mt": "mount"}

def normalize_city(name: str) -> str:
    """'St. Louis', 'saint louis' and '  ST LOUIS ' all become 'saint louis'."""
    name = name.lower().replace(".", " ")
    words = [ABBREVIATIONS.get(word, word) for word in name.split()]
    return " ".join(words)


@cache
def load_cities() -> dict[tuple[str, str], tuple[float, float]]:
    """Read the city file once; later calls return the same dictionary."""
    
    cities = {}
    
    with open(CITIES_FILE, newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            key = (row["STATE_CODE"], normalize_city(row["CITY"]))
            if key not in cities:  # a few names repeat within a state; keep the first
                cities[key] = (float(row["LATITUDE"]), float(row["LONGITUDE"]))
    
    # Hand-checked fixes: towns missing from the list, or placed wrongly in it
    with open(OVERRIDES_FILE, newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            key = (row["state"], normalize_city(row["city"]))
            cities[key] = (float(row["latitude"]), float(row["longitude"]))
    
    return cities


def find_city(city: str, state: str) -> tuple[float, float] | None:
    """Return (latitude, longitude) for a US city, or None if unknown."""
    
    key = (state.strip().upper(), normalize_city(city))
    
    return load_cities().get(key)