"""
Data-transfer objects used between the routing layers.

These are plain dataclasses with no Django dependencies — they can be
unit-tested without a database.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float


@dataclass(frozen=True)
class CorridorStation:
    """A station projected onto the route, within the corridor."""
    id: int
    name: str
    city: str
    state: str
    lat: float
    lon: float
    price: Decimal
    distance_along_route: float   # miles from start
    distance_off_route: float     # perpendicular distance, miles
    # Class-level default so the optimizer can treat all nodes uniformly
    is_virtual: bool = False
    @property
    def distance(self) -> float:
        """Alias so optimizer can treat all nodes uniformly."""
        return self.distance_along_route


@dataclass(frozen=True)
class FuelPurchase:
    station_id: Optional[int]
    station_name: str
    city: str
    state: str
    lat: float
    lon: float
    price: Decimal
    distance_from_start_miles: float
    gallons: Decimal
    cost_usd: Decimal


@dataclass(frozen=True)
class OptimizationResult:
    stops: List[FuelPurchase]
    total_cost_usd: Decimal
    total_gallons_consumed: Decimal