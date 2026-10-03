"""
Unit tests for the cost-optimal fuel-stop algorithm.

Every test is a pure function call — no DB, no network, no Django.
"""
from decimal import Decimal

import pytest

from core.exceptions import NoReachableFuelStationError
from routing.services.route_optimizer import select_optimal_stops


class TestShortRoutes:
    def test_route_fits_in_one_tank(self, make_station):
        """Route shorter than max range needs no fuel stops."""
        corridor = [
            make_station(id=1, price="3.00", distance_along_route=100),
        ]
        result = select_optimal_stops(
            corridor_stations=corridor,
            total_distance_miles=400,
            max_range_miles=500,
            mpg=10,
        )
        assert result.stops == []
        assert result.total_cost_usd == Decimal("0")
        assert result.total_gallons_consumed == Decimal("40.00")

    def test_route_exactly_at_range_limit(self, make_station):
        """Boundary: total == max_range → still no stops."""
        result = select_optimal_stops(
            corridor_stations=[],
            total_distance_miles=500,
            max_range_miles=500,
            mpg=10,
        )
        assert result.stops == []
        assert result.total_gallons_consumed == Decimal("50.00")


class TestLongRoutes:
    def test_no_stations_reachable_raises(self, make_station):
        """If the first station is beyond range, we cannot start."""
        corridor = [
            make_station(id=1, price="3.00", distance_along_route=600),
        ]
        with pytest.raises(NoReachableFuelStationError):
            select_optimal_stops(corridor, 1200, 500, 10)

    def test_stations_but_gap_too_large(self, make_station):
        """Gap between stations exceeds range."""
        corridor = [
            make_station(id=1, price="3.00", distance_along_route=400),
            make_station(id=2, price="3.00", distance_along_route=1000),  # 600 mi gap
        ]
        with pytest.raises(NoReachableFuelStationError):
            select_optimal_stops(corridor, 1500, 500, 10)

    def test_picks_cheapest_reachable(self, make_station):
        """With two reachable stations, algorithm goes to the cheaper one."""
        corridor = [
            make_station(id=1, price="3.00", distance_along_route=200),
            make_station(id=2, price="2.50", distance_along_route=400),  # cheaper
        ]
        # 900 mi route. Start full (500). Cheap station at 400 mi is reachable.
        result = select_optimal_stops(corridor, 900, 500, 10)

        assert len(result.stops) == 1
        assert result.stops[0].station_id == 2       # skipped the expensive one
        assert result.stops[0].price == Decimal("2.50")
        # Needed to reach finish (900 - 400 = 500 mi). Had 100 mi left → buy 400 mi.
        assert result.stops[0].gallons == Decimal("40.000")
        assert result.stops[0].cost_usd == Decimal("100.00")

    def test_look_ahead_buys_only_enough_to_reach_cheaper(self, make_station):
        """
        When a cheaper station is ahead, buy just enough to reach it —
        not a full tank.
        """
        corridor = [
            make_station(id=1, price="5.00", distance_along_route=100),
            make_station(id=2, price="2.00", distance_along_route=400),
        ]
        # 800 mi route.
        # At start, station 2 (cheaper) is reachable → go straight there.
        # At station 2, need to reach finish (800 mi). Bought 40 gallons.
        result = select_optimal_stops(corridor, 800, 500, 10)

        # Should only stop at the cheap station, not the expensive one
        assert len(result.stops) == 1
        assert result.stops[0].station_id == 2

    def test_all_same_price_fills_tank(self, make_station):
        """With no cheaper station ahead, fill up fully at each stop."""
        corridor = [
            make_station(id=1, price="3.00", distance_along_route=400),
        ]
        # 1000 mi route, one station at 400.
        # Start → reach station 1 (400 mi) with 100 mi in tank.
        # Fill to 500 mi (buy 400 mi = 40 gal). Drive 600 mi to finish — can't!
        # Wait, 500 is not enough for 600. Station 1 at 400, finish at 1000.
        # From station 1, 600 mi remain but max range is 500.
        # No station after 400 → should raise.
        with pytest.raises(NoReachableFuelStationError):
            select_optimal_stops(corridor, 1000, 500, 10)

    def test_multiple_stops_all_same_price(self, make_station):
        """No cheaper stations — algorithm fills up at each."""
        corridor = [
            make_station(id=1, price="3.00", distance_along_route=200),
            make_station(id=2, price="3.00", distance_along_route=600),
            make_station(id=3, price="3.00", distance_along_route=1000),
        ]
        result = select_optimal_stops(corridor, 1200, 500, 10)

        # Total consumed: 1200 mi / 10 = 120 gal.
        # Start full (50 gal assumed pre-purchased, not reported).
        # Stops fill the remainder.
        assert len(result.stops) == 3
        total_gallons_bought = sum(s.gallons for s in result.stops)
        assert total_gallons_bought == Decimal("70.000")   # 120 - 50 initial
        assert result.total_gallons_consumed == Decimal("120.00")


class TestCorridorEdgeCases:
    def test_station_exactly_at_start(self, make_station):
        """A station at mile 0 with a full tank: no reason to stop."""
        corridor = [
            make_station(id=1, price="5.00", distance_along_route=0.0),
            make_station(id=2, price="2.00", distance_along_route=400),
        ]
        result = select_optimal_stops(corridor, 800, 500, 10)
        # Should skip station 1 entirely (start tank is "free")
        assert all(s.station_id != 1 for s in result.stops)

    def test_station_exactly_at_finish(self, make_station):
        """Station at the destination is useless."""
        corridor = [
            make_station(id=1, price="2.00", distance_along_route=800),
            make_station(id=2, price="5.00", distance_along_route=400),
        ]
        # 800 mi route. Station 2 at 400 is reachable. Station 1 at finish (800) is not.
        result = select_optimal_stops(corridor, 800, 500, 10)
        assert len(result.stops) == 1
        assert result.stops[0].station_id == 2   # forced to buy at the expensive one