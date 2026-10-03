"""
Shared pytest fixtures.
"""
import math
from decimal import Decimal

import pytest

from routing.dtos import CorridorStation
from core.interfaces.routing import RouteResult


# ----------------------------------------------------------------------
# Autouse: reset caches & singletons between every test
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_caches():
    """
    Runs before AND after every test.
    Clears:
      - Django cache (route cache)
      - StationIndex in-memory singleton
    Prevents cross-test leakage.
    """
    from django.core.cache import cache
    from routing.services.station_index import invalidate_station_index

    cache.clear()
    invalidate_station_index()
    yield
    cache.clear()
    invalidate_station_index()


# ----------------------------------------------------------------------
# Domain fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def make_station():
    """Factory for CorridorStation instances with sensible defaults."""
    def _make(
        id=1,
        name="TEST STATION",
        city="Testville",
        state="TX",
        lat=30.0,
        lon=-97.0,
        price="3.00",
        distance_along_route=0.0,
        distance_off_route=0.5,
    ):
        return CorridorStation(
            id=id, name=name, city=city, state=state,
            lat=lat, lon=lon, price=Decimal(price),
            distance_along_route=distance_along_route,
            distance_off_route=distance_off_route,
        )
    return _make


# ----------------------------------------------------------------------
# Routing fixtures
# ----------------------------------------------------------------------
def _interpolate_straight_line(start, finish, num_points=50):
    return [
        (
            start[0] + (finish[0] - start[0]) * i / (num_points - 1),
            start[1] + (finish[1] - start[1]) * i / (num_points - 1),
        )
        for i in range(num_points)
    ]


def _haversine(a, b):
    R = 3958.7613
    lat1, lon1 = a
    lat2, lon2 = b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


@pytest.fixture
def fake_route_result():
    """Build a RouteResult along a straight line, distance from haversine."""
    def _make(start, finish, distance_miles=None):
        coords = _interpolate_straight_line(start, finish, num_points=50)
        if distance_miles is None:
            # Sum haversine of each segment → matches projector's cumulative distance
            distance_miles = sum(
                _haversine(coords[i], coords[i + 1]) for i in range(len(coords) - 1)
            )
        return RouteResult(
            distance_miles=distance_miles,
            duration_seconds=distance_miles * 72,   # ~50 mph
            coordinates=coords,
        )
    return _make


@pytest.fixture
def point_on_line():
    """Helper: returns (lat, lon) at fraction t along start→finish."""
    def _point(start, finish, t):
        return (
            start[0] + (finish[0] - start[0]) * t,
            start[1] + (finish[1] - start[1]) * t,
        )
    return _point