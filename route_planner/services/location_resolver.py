from dataclasses import dataclass

from route_planner.services.city_lookup import find_city
from route_planner.services.us_states import MAINLAND_STATES, NAME_TO_CODE, US_STATES


class LocationError(ValueError):
    """The user's location can't be understood or isn't supported."""

@dataclass(frozen=True)
class Place:
    label: str
    latitude: float
    longitude: float

def split_city_state(text: str) -> tuple[str, str]:
    """'Dallas, TX' or 'Dallas, Texas' -> ('Dallas', 'TX')."""
    
    if "," not in text:
        raise LocationError(f"'{text}': use the format 'City, ST', e.g. 'Dallas, TX'.")

    city, state = text.rsplit(",", 1)
    city = " ".join(city.split())
    state = " ".join(state.split())

    code = state.upper() if len(state) == 2 else NAME_TO_CODE.get(state.lower())


    if not city or code not in US_STATES:
        raise LocationError(f"'{text}': unknown state '{state}'. Use a code like TX or a name like Texas.")

    return city, code

def resolve_location(text: str) -> Place:
    """'Dallas, TX' -> Place('Dallas, TX', 32.78, -96.80), or raise LocationError."""
    
    city, state = split_city_state(text)

    if state not in MAINLAND_STATES:
        raise LocationError(
            f"'{text}': only the 48 mainland states and DC are supported "
            "(no fuel price data for Alaska or Hawaii)."
        )

    coordinates = find_city(city, state)
    
    if coordinates is None:
        raise LocationError(f"'{text}': city not found in {state}. Check the spelling.")

    latitude, longitude = coordinates
    
    return Place(label=f"{city}, {state}", latitude=latitude, longitude=longitude)