"""Turns the user's text ("Chicago, IL") into a place on the map."""

from dataclasses import dataclass

from route_planner.services.city_lookup import CityLookup
from route_planner.services.us_states import MAINLAND_STATES, NAME_TO_CODE, STATE_NAMES, US_STATES


class LocationError(ValueError):
    """The text can't be turned into a supported place."""


@dataclass(frozen=True)
class Place:
    label: str
    latitude: float
    longitude: float


class LocationResolver:
    """Accepts "City, ST" or "City, State name", on the US mainland (lower 48 + DC)."""

    def __init__(self, city_lookup: CityLookup | None = None):
        self.city_lookup = city_lookup or CityLookup()

    def resolve(self, text: str) -> Place:
        """"Chicago, IL" -> Place("Chicago, IL", 41.84, -87.68), or a LocationError."""
        
        city, state = self.split_city_state(text)

        if state not in MAINLAND_STATES:
            raise LocationError(
                f"{STATE_NAMES[state]} is not supported: the price data covers the mainland US only."
            )

        coordinates = self.city_lookup.find(city, state)
        if coordinates is None:
            raise LocationError(f"{city} not found in {state}. Check the spelling.")

        latitude, longitude = coordinates
        return Place(label=f"{city}, {state}", latitude=latitude, longitude=longitude)

    @staticmethod
    def split_city_state(text: str) -> tuple[str, str]:
        """"chicago ,  il" -> ("chicago", "IL"). Accepts a state code or a full state name."""
        
        if "," not in text:
            raise LocationError(f'"{text}": use the format "City, ST", for example "Chicago, IL".')

        city, state = text.rsplit(",", 1)
        city = " ".join(city.split())
        state = " ".join(state.split())

        if len(state) == 2:
            state = state.upper()
        else:
            state = NAME_TO_CODE.get(state.lower(), state)

        if state not in US_STATES:
            raise LocationError(f'"{state}" is not a US state. Use a code like "IL" or a name like "Illinois".')
        if not city:
            raise LocationError(f'"{text}": the city name is missing.')

        return city, state