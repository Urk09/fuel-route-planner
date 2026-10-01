# Fuel Route Planner

A Django REST API that takes a start and a finish in the USA and returns:

- the driving route, as a map (GeoJSON),
- the cheapest places to buy fuel along the way (500-mile range, 10 miles per gallon),
- the total fuel cost.

It calls the routing API **once per new trip**. Repeat trips are served from a Redis cache, with no API call.

**Stack:** Python 3.13 · Django 6.1 · Django REST Framework 3.18 · PostgreSQL 17 · Redis 7 · gunicorn · Docker · uv · OpenRouteService (routing)

---

## Quick start (Docker)

You need Docker and a free OpenRouteService API key ([sign up here](https://openrouteservice.org/dev/#/signup)).

```bash
git clone https://github.com/<your-username>/fuel-route-planner.git
cd fuel-route-planner
cp .env.example .env          # then put your key in OPEN_ROUTE_SERVICE_API_KEY
docker compose up --build
```

The API is now on **http://127.0.0.1:8000**. On every start, the app creates its tables, loads the 6,626 fuel stations (safe to repeat) and starts gunicorn.

Run the tests inside the container:

```bash
docker compose exec web python manage.py test route_planner     # 25 tests
```

---

## Using the API

### Request

`POST /api/v1/trip-plan/`

```bash
curl -X POST http://127.0.0.1:8000/api/v1/trip-plan/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "St. Louis, MO"}'
```

Places are written as `"City, ST"` or `"City, State name"` (for example `"St. Louis, Missouri"`). Mainland USA only: the price data has no stations in Alaska or Hawaii.

**Optional:** `"skip_small_stops": true` avoids stops that would buy only a little fuel (see "The fuel algorithm"). The default is `false`: the plan is the cheapest to the cent.

```json
{"start": "Chicago, IL", "finish": "St. Louis, MO", "skip_small_stops": true}
```

A ready-made **Postman collection** is in [`postman/`](postman/), with example trips and every error case.

### Response (shortened)

```json
{
  "start":  {"label": "Chicago, IL",   "latitude": …, "longitude": …},
  "finish": {"label": "St. Louis, MO", "latitude": …, "longitude": …},
  "distance_miles": 305.7,
  "duration_hours": …,
  "vehicle": {"range_miles": 500.0, "miles_per_gallon": 10.0},
  "skip_small_stops": false,
  "fuel_stops": [
    {
      "station_id": …,
      "name": "…",
      "address": "…",
      "city": "…",
      "state": "IL",
      "mile": 14.0,
      "price_per_gallon": "3.079",
      "gallons": "29.17",
      "cost": "89.80",
      "off_route_miles": …,
      "location_precision": "city",
      "route_point": {"latitude": …, "longitude": …}
    }
  ],
  "total_gallons": "30.57",
  "total_fuel_cost": "94.56",
  "notes": [],
  "map": {"type": "FeatureCollection", "features": ["the road, the start, the finish, every fuel stop"]}
}
```

- **Money, prices and gallons are text** (`"94.56"`) so they stay exact. JSON numbers are floats and can come out as `94.56000000000001`.
- **`total_fuel_cost` is the sum of the rounded stop costs**, so the numbers on screen always add up.
- **`map`** is the whole trip in GeoJSON, the standard map format: the road, the start, the finish and every fuel stop with its details. Any map tool can draw it: for example, paste it into [geojson.io](https://geojson.io).
- **`notes`** explains any assumption the plan had to make (see "Start of the trip" below).

### Errors

Every error has the same shape: `{"detail": "..."}`, or the field name for a missing field.

| Code | Meaning | Example |
|---|---|---|
| **400** | The request is broken | missing `finish`, invalid JSON |
| **422** | The request is fine, but this trip can't be planned | unknown city, Alaska, no road between the places, a gap of more than 500 miles with no station |
| **503** | The routing service is down, slow or out of quota (not the caller's fault) | OpenRouteService unreachable |

---

## How it works

```
"Chicago, IL"  →  place on the map     offline city list, no API call
               →  route                OpenRouteService, one call; cached in Redis for 30 days
               →  stations near road   every station within 10 miles of the road (grid search)
               →  fuel plan            the cheapest way to buy fuel for the trip
               →  JSON + GeoJSON map
```

**Routes stay inside the US** (`avoid_borders`), because the price data is US-only. For example, Detroit → Buffalo goes around Lake Erie (360 miles) instead of through Ontario (262 miles).

All of this is in `TripPlanner.plan()` (`route_planner/services/trip_planner.py`). The view only handles HTTP: it checks the input, calls the planner and turns errors into status codes.

### The fuel algorithm

**In one line: cover the most miles with the cheapest fuel.**

Stations are laid out along the route by mile marker. At each station:

1. **Cheaper station within reach?** Buy just enough to get there.
2. **Finish within reach?** Buy just enough to finish.
3. **Otherwise,** fill up and drive to the cheapest station within reach.
4. **No station within 500 miles?** The trip is impossible: a clear 422 error says between which miles.

This is the classic greedy solution to the "gas station problem", and it is exactly optimal for this model. I checked it against an exact linear-programming solver on 300 random trips: same cost every time.

Assumptions (all from the brief, or stated here):

- **Start of the trip:** the tank starts empty and is filled at the cheapest station within 10 miles of the start. If there is none, the plan assumes a full tank at departure, says so in `notes`, and doesn't charge for it.
- **Several stations at the same spot:** only the cheapest is used.
- **Detours are not charged.** Each stop shows `off_route_miles`, how far the station is from the road.
- **No safety margin:** the plan uses the full 500-mile range, as the brief describes.

Real results: Chicago → St. Louis is 305.7 miles, 4 stops, $94.56. New York → Los Angeles is 2,795.8 miles, 18 stops, 279.58 gallons, $847.77.

**Skipping small stops (optional).** Because the plan is optimal to the cent, it can stop for a tiny amount when a slightly cheaper station is very close: Chicago → St. Louis has two stops worth $0.01–0.02. With `"skip_small_stops": true`, every stop must buy at least 10% of a tank (5 gallons for this car). The planner makes the cheapest plan, finds a stop that buys less, drops that station and plans again. A small stop is kept only when the trip is impossible without it, and the first fill-up is never skipped (the tank starts empty). Chicago → St. Louis goes from 4 stops to 2, for about a cent more. The minimum is a share of the tank, so a bigger truck tank gets a bigger minimum.

### Finding the stations near the route

A coast-to-coast route has about 21,500 road points, and there are 6,626 stations. Checking every station against every point took about 9 seconds even for Chicago → St. Louis. Instead, the route points are put into a grid of squares at least 10 miles wide, and each station is only compared with the points in its own square and the 8 around it: **0.05 s for Chicago → St. Louis, 0.15 s coast to coast.**

### Caching

Only the **route** is cached, not the whole answer, so prices and stops are always worked out fresh. If the price file is reloaded, the next answer uses the new prices.

- **Key:** the start and finish coordinates plus the vehicle profile, so "Chicago, IL" and "chicago, illinois" share one entry.
- **Lifetime:** 30 days (roads rarely change). Errors are never cached.
- **Speed:** first request 1–2 s (mostly OpenRouteService), repeat request 100–200 ms.
- **If Redis is down,** the API still works and calls OpenRouteService directly, with a warning in the log. The cache is a speed-up, never a reason to fail.

`CachedRoutingClient` wraps the real client and has the same `get_route()` method, so the planner doesn't know the cache exists.

---

## The fuel price file: what I found and how it's handled

The provided file has 8,151 rows.

- **620 rows are Canadian stations.** They were dropped: the routes are US-only.
- **568 stations appear several times with different prices and no date.** The lowest price is kept.
- **Extra spaces** in names, addresses and cities are trimmed.
- **Result: 6,626 US stations.** Re-running `load_stations` is safe: existing stations are updated, not duplicated.

**Locations.** The price file has no station coordinates, so each station is placed at its city's location from a free US city dataset (median error ~1 mile, 94% within 5 miles, 98% within 10 miles). When accurate station coordinates are available, re-running `load_stations` updates every station, and nothing else changes.

That is why "near the route" means within 10 miles of the road: it absorbs the city-level location error. Each stop is marked `"location_precision": "city"`, and its map marker is placed on the road next to the station.

7 cities needed a hand-checked fix: a different spelling, a neighbourhood, a county, three cities missing from the list, and one duplicate placed 48 miles away. Each fix comes from Wikipedia and is listed with its reason in `data/city_overrides.csv`.

**Coverage:** some states have very few stations in the file (California 8, Oregon 29, Washington 52), so some West Coast trips may not have enough stations. The API then says so with a clear 422 error.

## Tests

25 tests. They need no network, no API key, no quota and no Redis.

| File | Tests | What they check |
|---|---|---|
| `test_optimizer.py` | 11 | the fuel algorithm: cheaper fuel ahead, fill-ups, exactly 500 miles works, 501 fails, no station at the start, gallons = miles ÷ 10, vehicle settings, skipping small stops (and keeping one the trip needs) |
| `test_api.py` | 9 | the endpoint with a fake routing client: the plan, the numbers add up, the map, the `skip_small_stops` option, and every error code |
| `test_route_cache.py` | 5 | repeat trips skip the API, the same place typed differently, errors not cached, Redis down still works |

---

## Project layout

```
config/                        settings (from environment variables), URLs
route_planner/
  models.py                    FuelStation
  serializers.py               checks the request, shapes the response and the GeoJSON map
  views.py                     POST /api/v1/trip-plan/, errors → status codes
  services/
    trip_planner.py            TripPlanner: runs every step
    location_resolver.py       "City, ST" → place
    city_lookup.py             offline US city list + hand-checked overrides
    routing_api.py             OpenRouteServiceClient
    route_cache.py             CachedRoutingClient (Redis)
    stations_on_route.py       StationFinder (grid search)
    optimizer.py               FuelPlanner (the fuel algorithm)
    geo.py                     distance on the Earth's surface
    us_states.py               state codes and names
  management/commands/
    load_stations.py           price CSV → database (safe to re-run)
  tests/                       25 tests
data/                          price file, US city list (+ its licence), city overrides
postman/                       Postman collection
Dockerfile, docker-compose.yml, docker-compose.dev.yml
```

---

## What I'd improve next

- **A cost per stop:** trade fewer stops against fuel cost (NY → LA has 18 stops; 6–8 would be enough at a slightly higher cost).
- **A fuel reserve** (never plan to arrive empty) and **charging for detours**.
- **More accurate station locations** (exact exit coordinates), and addresses or coordinates as input.
- **Truck routing:** OpenRouteService's `driving-hgv` profile plus a truck `FuelPlanner`.
- **Simplify the route line** before sending it (NY → LA is about 0.5 MB).
- **A small web page** (Leaflet) that draws the API's GeoJSON map.
- **Resilience:** a backup routing provider, and a second route store in Postgres if the daily quota becomes the limit. It fits the current design as one more wrapper: `CachedRoutingClient(StoredRoutingClient(OpenRouteServiceClient()))`.
- **CI** (tests on every push) and **deployment** (e.g. GCP).

---

## Data sources

- **Fuel prices:** provided with the assignment (`data/fuel-prices-for-be-assessment.csv`).
- **US cities:** [US-Cities-Database by Kelvins](https://github.com/kelvins/US-Cities-Database), MIT licence (`data/LICENSE.us_cities`).
- **City fixes:** Wikipedia (sources listed in `data/city_overrides.csv`).
- **Routing:** [OpenRouteService](https://openrouteservice.org), using OpenStreetMap data © OpenStreetMap contributors.