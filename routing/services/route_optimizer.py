"""
Cost-optimal fuel-stop selection.

Algorithm (classic "gas station problem"):
  Sort stations by distance along route. At each station we stop at:
    - If a CHEAPER station is reachable within max_range ahead:
        buy just enough fuel to reach it.
    - Otherwise:
        fill the tank completely and drive to the cheapest reachable station.

Assumption: vehicle starts with a full tank at mile 0 (cost of that initial
tank is excluded from the reported total — we report refueling costs only).
If the route is short enough to complete on the initial tank, no stops are
returned and total cost is $0.
"""
from decimal import Decimal
from typing import List, Optional, Tuple

from core.exceptions import NoReachableFuelStationError
from routing.dtos import CorridorStation, FuelPurchase, OptimizationResult


def select_optimal_stops(
    corridor_stations: List[CorridorStation],
    total_distance_miles: float,
    max_range_miles: int,
    mpg: int,
) -> OptimizationResult:
    # Sort by position along route
    stations = sorted(corridor_stations, key=lambda s: s.distance_along_route)

    # Sanity: if route fits in one tank, no fuel stops needed
    if total_distance_miles <= max_range_miles:
        return OptimizationResult(
            stops=[],
            total_cost_usd=Decimal("0"),
            total_gallons_consumed=(Decimal(str(total_distance_miles)) / Decimal(mpg)).quantize(Decimal("0.01")),
        )

    # Virtual stations to anchor the algorithm.
    # price=0 ensures they act as "cheapest" for the look-ahead.
    start = _VirtualStation(distance=0.0, price=Decimal("0"))
    finish = _VirtualStation(distance=float(total_distance_miles), price=Decimal("0"))
    ordered = [start] + stations + [finish]

    fuel_miles: float = float(max_range_miles)   # start with a full tank
    purchases: List[FuelPurchase] = []
    total_cost = Decimal("0")

    i = 0
    guard = 0
    while i < len(ordered) - 1:
        guard += 1
        if guard > len(ordered) + 5:
            raise RuntimeError("Optimizer failed to converge — likely a bug.")

        current = ordered[i]
        if current.distance >= total_distance_miles:
            break

        # ---- Look-ahead: nearest cheaper station within max_range ----
        next_cheaper_idx: Optional[int] = None
        for j in range(i + 1, len(ordered)):
            candidate = ordered[j]
            if candidate.distance - current.distance > max_range_miles:
                break
            if candidate.price < current.price:
                next_cheaper_idx = j
                break

        if next_cheaper_idx is not None:
            target = ordered[next_cheaper_idx]
            dist_to_target = target.distance - current.distance
            buy_miles = max(0.0, dist_to_target - fuel_miles)

            if buy_miles > 0 and not current.is_virtual:
                gallons = (Decimal(str(buy_miles)) / Decimal(mpg)).quantize(Decimal("0.001"))
                cost = (gallons * current.price).quantize(Decimal("0.01"))
                purchases.append(FuelPurchase(
                    station_id=current.id, station_name=current.name,
                    city=current.city, state=current.state,
                    lat=current.lat, lon=current.lon, price=current.price,
                    distance_from_start_miles=round(current.distance, 2),
                    gallons=gallons, cost_usd=cost,
                ))
                total_cost += cost
                fuel_miles += buy_miles

            fuel_miles -= dist_to_target
            i = next_cheaper_idx

        else:
            # ---- Fill up completely ----
            if not current.is_virtual:
                fill_miles = float(max_range_miles) - fuel_miles
                if fill_miles > 0:
                    gallons = (Decimal(str(fill_miles)) / Decimal(mpg)).quantize(Decimal("0.001"))
                    cost = (gallons * current.price).quantize(Decimal("0.01"))
                    purchases.append(FuelPurchase(
                        station_id=current.id, station_name=current.name,
                        city=current.city, state=current.state,
                        lat=current.lat, lon=current.lon, price=current.price,
                        distance_from_start_miles=round(current.distance, 2),
                        gallons=gallons, cost_usd=cost,
                    ))
                    total_cost += cost
                    fuel_miles = float(max_range_miles)

            # ---- Drive to cheapest reachable station ----
            cheapest_idx = None
            cheapest_price = None
            for j in range(i + 1, len(ordered)):
                cand = ordered[j]
                if cand.distance - current.distance > fuel_miles:
                    break
                if cheapest_price is None or cand.price < cheapest_price:
                    cheapest_price = cand.price
                    cheapest_idx = j

            if cheapest_idx is None:
                raise NoReachableFuelStationError(
                    f"No fuel station reachable from mile {current.distance:.1f} "
                    f"(range {fuel_miles:.1f} mi). Cannot complete the route."
                )

            target = ordered[cheapest_idx]
            fuel_miles -= (target.distance - current.distance)
            i = cheapest_idx

    total_gallons = (Decimal(str(total_distance_miles)) / Decimal(mpg)).quantize(Decimal("0.01"))

    return OptimizationResult(
        stops=purchases,
        total_cost_usd=total_cost.quantize(Decimal("0.01")),
        total_gallons_consumed=total_gallons,
    )


# ----------------------------------------------------------------------
class _VirtualStation:
    """Sentinel for start/finish nodes in the optimization chain."""
    __slots__ = ("distance", "price", "is_virtual", "id", "name", "city", "state", "lat", "lon")

    def __init__(self, distance: float, price: Decimal):
        self.distance = distance
        self.price = price
        self.is_virtual = True
        self.id = None
        self.name = "—"
        self.city = "—"
        self.state = "—"
        self.lat = 0.0
        self.lon = 0.0