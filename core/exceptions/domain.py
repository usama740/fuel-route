from rest_framework import status
from .base import FuelRouteError


class InvalidLocationError(FuelRouteError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "One or both locations are outside the USA or invalid."
    default_code = "invalid_location"


class RouteNotFoundError(FuelRouteError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "No drivable route could be found between the given locations."
    default_code = "route_not_found"


class NoReachableFuelStationError(FuelRouteError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "The vehicle cannot complete the route within its 500-mile range."
    default_code = "no_reachable_station"


class RoutingProviderError(FuelRouteError):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "The external routing service is unavailable."
    default_code = "routing_provider_error"


class GeocodingProviderError(FuelRouteError):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "The external geocoding service is unavailable."
    default_code = "geocoding_provider_error"