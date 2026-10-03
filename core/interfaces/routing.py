"""
Abstract contract for routing providers.

Concrete implementations live in routing/repositories/ (e.g. the ORS adapter).
The domain layer depends ONLY on this interface, never on a concrete provider.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class RouteResult:
    """Immutable result of a routing query."""
    distance_miles: float
    duration_seconds: float
    coordinates: List[Tuple[float, float]]   # [(lat, lon), ...] in route order


class RouteGeometryProvider(ABC):
    """Anything that can produce a drivable route between two points."""

    @abstractmethod
    def get_route(
        self,
        start: Tuple[float, float],
        finish: Tuple[float, float],
    ) -> RouteResult:
        """
        start, finish: (lat, lon) tuples.
        Raises RoutingProviderError on provider failure.
        """
        ...