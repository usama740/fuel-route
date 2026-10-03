import hashlib
import logging
from typing import Tuple

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import RouteNotFoundError
from routing.dtos import CorridorStation
from routing.providers.openrouteservice import OpenRouteServiceProvider
from routing.services.geocoder import LocationResolver
from routing.services.route_optimizer import select_optimal_stops
from routing.services.route_projector import RouteProjector
from routing.services.station_index import get_station_index
from .serializers import RoutePlanRequestSerializer, RoutePlanResponseSerializer

logger = logging.getLogger(__name__)


class RoutePlanView(APIView):
    """POST /api/v1/route/plan-fuel-stops/"""

    def post(self, request):
        req = RoutePlanRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)

        start = self._resolve_location(req.validated_data["start"])
        finish = self._resolve_location(req.validated_data["finish"])

        route = self._get_route_cached(start, finish)

        if route.distance_miles <= 0:
            raise RouteNotFoundError()

        projector = RouteProjector(route.coordinates)
        station_index = get_station_index()

        corridor_stations = self._build_corridor(
            projector=projector,
            station_index=station_index,
            corridor_miles=settings.STATION_CORRIDOR_MILES,
        )

        result = select_optimal_stops(
            corridor_stations=corridor_stations,
            total_distance_miles=route.distance_miles,
            max_range_miles=settings.VEHICLE_MAX_RANGE_MILES,
            mpg=settings.VEHICLE_MPG,
        )

        payload = self._serialize_response(route, start, finish, result)
        out = RoutePlanResponseSerializer(payload)
        return Response(out.data, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_location(loc: dict) -> Tuple[float, float]:
        """Coords pass through; strings resolved via local GeocodeCache."""
        if loc["source"] == "coords":
            return loc["lat"], loc["lon"]
        return LocationResolver().resolve(loc["query"])

    # ------------------------------------------------------------------
    def _get_route_cached(self, start, finish):
        key = self._cache_key(start, finish)
        cached = cache.get(key)
        if cached is not None:
            return cached

        router = OpenRouteServiceProvider()
        route = router.get_route(start, finish)
        cache.set(key, route, timeout=60 * 60 * 24)
        return route

    @staticmethod
    def _cache_key(start, finish) -> str:
        raw = f"{start[0]:.4f},{start[1]:.4f}|{finish[0]:.4f},{finish[1]:.4f}"
        return "route:" + hashlib.sha256(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    @staticmethod
    def _build_corridor(projector, station_index, corridor_miles):
        stations = station_index.all_stations()
        result = []
        for s in stations:
            along, off = projector.project(s.latitude, s.longitude)
            if off <= corridor_miles:
                result.append(CorridorStation(
                    id=s.id, name=s.name, city=s.city, state=s.state,
                    lat=s.latitude, lon=s.longitude,
                    price=s.retail_price,
                    distance_along_route=along,
                    distance_off_route=off,
                ))
        logger.info(
            "Corridor: %d of %d stations within %.1f mi of route",
            len(result), len(stations), corridor_miles,
        )
        return result

    # ------------------------------------------------------------------
    @staticmethod
    def _serialize_response(route, start, finish, result):
        return {
            "route": {
                "distance_miles": round(route.distance_miles, 2),
                "duration_seconds": round(route.duration_seconds, 1),
                "geometry": [[lat, lon] for lat, lon in route.coordinates],
                "start": {"lat": start[0], "lon": start[1]},
                "finish": {"lat": finish[0], "lon": finish[1]},
            },
            "fuel_stops": [
                {
                    "order": idx + 1,
                    "station_id": p.station_id,
                    "name": p.station_name,
                    "city": p.city,
                    "state": p.state,
                    "latitude": p.lat,
                    "longitude": p.lon,
                    "retail_price": p.price,
                    "distance_from_start_miles": p.distance_from_start_miles,
                    "gallons_purchased": p.gallons,
                    "cost_usd": p.cost_usd,
                }
                for idx, p in enumerate(result.stops)
            ],
            "total_fuel_cost_usd": result.total_cost_usd,
            "total_gallons_consumed": result.total_gallons_consumed,
            "assumptions": {
                "vehicle_max_range_miles": settings.VEHICLE_MAX_RANGE_MILES,
                "fuel_efficiency_mpg": settings.VEHICLE_MPG,
            },
        }