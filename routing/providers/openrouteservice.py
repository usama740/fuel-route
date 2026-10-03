"""
Single-call ORS directions client. One call per (start, finish) pair.
"""
import logging
from typing import Optional, Tuple

import openrouteservice
from django.conf import settings

from core.exceptions import RoutingProviderError
from core.interfaces.routing import RouteGeometryProvider, RouteResult

logger = logging.getLogger(__name__)


class OpenRouteServiceProvider(RouteGeometryProvider):
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or settings.ORS_API_KEY
        if not key:
            raise RoutingProviderError("ORS_API_KEY is not configured.")
        self._client = openrouteservice.Client(key=key)

    def get_route(self, start: Tuple[float, float], finish: Tuple[float, float]) -> RouteResult:
        """
        start, finish: (lat, lon) tuples.
        Returns a RouteResult with geometry as [(lat, lon), ...].
        """
        try:
            resp = self._client.directions(
                # ORS expects [lon, lat] order
                coordinates=[[start[1], start[0]], [finish[1], finish[0]]],
                profile="driving-car",
                format="geojson",
                units="mi",
            )
        except Exception as exc:
            logger.exception("ORS directions call failed")
            raise RoutingProviderError(f"Routing provider error: {exc}") from exc

        try:
            feature = resp["features"][0]
            coords = feature["geometry"]["coordinates"]  # [[lon, lat], ...]
            summary = feature["properties"]["summary"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RoutingProviderError(f"Unexpected ORS response shape: {exc}") from exc

        latlon_coords = [(c[1], c[0]) for c in coords]  # → (lat, lon)

        return RouteResult(
            distance_miles=float(summary["distance"]),
            duration_seconds=float(summary["duration"]),
            coordinates=latlon_coords,
        )