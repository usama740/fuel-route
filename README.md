# Fuel Route API

A Django REST API that takes a start and finish location within the USA,
returns the driving route, and computes the **cost-optimal fuel stops** given
a vehicle with a 500-mile range and 10 mpg efficiency.

Built for the Route/Fuel assessment. Uses **one external routing API call per
unique route** (OpenRouteService), with all other data (station locations,
prices) served from a pre-loaded local database.

---

## Quick Start

```bash
# 1. Clone and enter
git clone <your-repo-url> fuel-route-api && cd fuel-route-api

# 2. Set up Python env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env
# Edit .env and set ORS_API_KEY (free key: https://openrouteservice.org/dev/#/signup)

# 4. Apply migrations
python manage.py migrate

# 5. Load reference data (one-time, ~10 seconds, no API calls)
python manage.py load_static_cities --file data/reference/us_cities.csv
python manage.py load_fuel_prices  --file data/fuel-prices-for-be-assessment.csv

# 6. Run
python manage.py runserver
```

## API Contract

### `POST /api/v1/route/plan-fuel-stops/`

Accepts **either** format for `start` and `finish`:

**Form A — human-readable (recommended for demos):**

```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA"
}
```

**Form B — precise coordinates:**

```json
{
  "start": { "lat": 40.7128, "lon": -74.006 },
  "finish": { "lat": 34.0522, "lon": -118.2437 }
}
```

**Response (200):**

```json
{
  "route": {
    "distance_miles": 2789.4,
    "duration_seconds": 148320.0,
    "geometry": [[40.7128, -74.0060], ...],
    "start": {"lat": 40.7128, "lon": -74.0060},
    "finish": {"lat": 34.0522, "lon": -118.2437}
  },
  "fuel_stops": [
    {
      "order": 1,
      "station_id": 3421,
      "name": "KWIK TRIP #796",
      "city": "Tomah",
      "state": "WI",
      "latitude": 43.9786,
      "longitude": -90.5040,
      "retail_price": "3.287333",
      "distance_from_start_miles": 480.21,
      "gallons_purchased": "48.000",
      "cost_usd": "157.79"
    }
  ],
  "total_fuel_cost_usd": "1042.18",
  "total_gallons_consumed": "278.94",
  "assumptions": {
    "vehicle_max_range_miles": 500,
    "fuel_efficiency_mpg": 10
  }
}
```

**Error envelope (all 4xx/5xx):**

```json
{ "error": { "code": "invalid_location", "detail": "Could not resolve..." } }
```

| Code                     | HTTP | Meaning                                                      |
| ------------------------ | ---- | ------------------------------------------------------------ |
| `invalid_location`       | 400  | Location outside USA or unparseable                          |
| `route_not_found`        | 404  | No drivable route                                            |
| `no_reachable_station`   | 422  | Cannot complete route within 500 mi between any two stations |
| `routing_provider_error` | 502  | Upstream ORS unavailable                                     |

---

## How It Minimizes API Calls

The assignment says one routing call is ideal, 2–3 acceptable. We hit **1**:

| Concern                     | Strategy                                                                                     |
| --------------------------- | -------------------------------------------------------------------------------------------- |
| **Routing**                 | One ORS `directions()` call per unique route, cached 24h in Django's cache                   |
| **Station geocoding**       | Not an API. A static US-cities CSV is loaded into a local `GeocodeCache` table once at setup |
| **City-name input**         | Resolved from the local `GeocodeCache` (0 API calls for ~17k US cities)                      |
| **Station lookup on route** | In-memory KD-tree over all 5,687 geocoded stations — zero I/O                                |

**Net per request:** 1 ORS call cold / 0 calls warm (cache hit).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  HTTP Layer          api/views.py, api/serializers.py       │
├─────────────────────────────────────────────────────────────┤
│  Domain Services     routing/services/                      │
│    • route_optimizer.py    cost-optimal fuel stops         │
│    • route_projector.py    project stations onto route     │
│    • station_index.py      in-memory station cache         │
│    • geocoder.py           "City, ST" → (lat, lon)         │
├─────────────────────────────────────────────────────────────┤
│  Interfaces (ABCs)   core/interfaces/                       │
│    • routing.py            RouteGeometryProvider           │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure      routing/providers/, stations/models.py │
│    • openrouteservice.py   ORS adapter (only API client)   │
│    • Station, GeocodeCache ORM models                       │
└─────────────────────────────────────────────────────────────┘
```

**Layering rules enforced:**

- `core/interfaces/` contains only ABCs — no implementations.
- `routing/providers/` is the only place that talks to external APIs.
- `routing/services/` is pure logic — no Django, no HTTP, no ORM.
- `api/` is thin — serialization + orchestration only.

---

## The Fuel-Stop Algorithm

Classic "gas station problem" with look-ahead:

```
At each station S (walking forward along the route):
  1. Look for the CHEAPEST station reachable within the remaining range.
  2. If it's cheaper than S → buy just enough to reach it, skip S's competitors.
  3. Otherwise → fill the tank completely and drive to the cheapest reachable.

If no station is reachable and the finish is beyond range → raise
NoReachableFuelStationError (422).
```

This runs in **O(N log N)** over the corridor stations. For a cross-country
route it executes in ~5 ms.

Assumption: the vehicle starts with a full tank at mile 0. The cost of that
initial tank is not included in `total_fuel_cost_usd` — we report _refueling_
cost only.

---

## Ingestion (One-Time Setup)

Two management commands load reference data:

### 1. City coordinates (no API)

```bash
python manage.py load_static_cities --file data/reference/us_cities.csv
```

Loads ~17,000 US cities into `GeocodeCache`. Source: [world-cities CSV](https://github.com/joelacus/world-cities).

### 2. Fuel stations

```bash
python manage.py load_fuel_prices --file data/fuel-prices-for-be-assessment.csv
```

Parses the OPIS CSV, collapses duplicate `(opis_id, city, state)` rows to the
minimum price, filters out non-US entries, and joins against `GeocodeCache`
for coordinates.

Both commands are **idempotent** — re-running is safe and near-instant.

Expected output:

```
Stations:        6626
Geocoded:        5687  (86%)
```

The 939 stations without coordinates are small towns missing from the
cities CSV. They're excluded from the KD-tree at runtime — no crashes, no
stale data.

---

## Design Decisions

| Decision                                   | Rationale                                                                                                                            |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| **`Decimal` for prices, not `float`**      | Money math must be exact. `3.00733333` doesn't round-trip cleanly through float.                                                     |
| **Station coordinates pre-baked**          | Routing is the only per-request external call. Station lookups are local.                                                            |
| **Static CSV for geocoding**               | US city coordinates don't change. A 3 MB CSV beats 17k API calls.                                                                    |
| **Cache key rounds to 4 decimals (~11 m)** | Collapses near-identical requests without ever returning a materially wrong route.                                                   |
| **3-mile corridor**                        | Stations further than ~3 mi from the route aren't "on the route" in any meaningful sense. Configurable via `STATION_CORRIDOR_MILES`. |
| **Custom exception hierarchy**             | Every domain error maps to a specific HTTP status and a machine-readable `code`.                                                     |
| **`scipy.cKDTree` over PostGIS**           | No GDAL/GEOS dependency. Works identically on SQLite (dev) and Postgres (prod).                                                      |

---

## Running Tests

```bash
pytest
```

**37 tests, ~1.5 seconds, zero network calls.** Everything that touches ORS is
mocked; the geocode cache is seeded from fixtures; the routing provider is
replaced with a straight-line fake.

```
routing/tests/test_route_optimizer.py  .........   algorithm correctness
routing/tests/test_route_projector.py  .....       geometry
api/tests/test_serializers.py          ........     request contract
api/tests/test_endpoint.py             ........     full HTTP round-trip (mocked ORS)
stations/tests/test_load_fuel_prices.py ......     CSV ingestion
```

---

## Configuration

All via `.env` (see `.env.example`):

| Variable                  | Default | Purpose                                |
| ------------------------- | ------- | -------------------------------------- |
| `DJANGO_SECRET_KEY`       | —       | Required in production                 |
| `DJANGO_DEBUG`            | `True`  | Set to `False` in prod                 |
| `STATION_CORRIDOR_MILES`  | `3`     | Corridor width for "stations on route" |
| `VEHICLE_MAX_RANGE_MILES` | `500`   | Per the assignment                     |
| `VEHICLE_MPG`             | `10`    | Per the assignment                     |

---

## Stack

- Python 3.11+, Django 5.x, Django REST Framework
- `openrouteservice` SDK (routing only)
- `scipy.spatial.cKDTree` (spatial index)
- `pytest` + `pytest-django` (tests)
- SQLite by default; any Django-supported DB works

---

## Demo

See the accompanying Loom video for a 5-minute walkthrough.
