from rest_framework import status
from rest_framework.exceptions import APIException


class FuelRouteError(APIException):
    """Base for all domain errors. Never raised directly."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "An unexpected fuel-route error occurred."
    default_code = "fuel_route_error"