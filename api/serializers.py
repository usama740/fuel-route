"""
Request/response serializers.

The request accepts EITHER format for start/finish:
  - String: "New York, NY"
  - Object: {"lat": 40.7128, "lon": -74.0060}
"""
from rest_framework import serializers


class LocationField(serializers.Field):
    """
    Accepts EITHER:
      - a string: "New York, NY"
      - a dict:   {"lat": 40.7128, "lon": -74.0060}
    Normalizes both to {"lat": float, "lon": float, "source": ...}
    """

    def to_internal_value(self, data):
        if isinstance(data, dict):
            if "lat" not in data or "lon" not in data:
                raise serializers.ValidationError(
                    "Object form requires 'lat' and 'lon'."
                )
            try:
                lat = float(data["lat"])
                lon = float(data["lon"])
            except (TypeError, ValueError):
                raise serializers.ValidationError("lat/lon must be numbers.")
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                raise serializers.ValidationError("lat/lon out of valid range.")
            return {"lat": lat, "lon": lon, "source": "coords"}

        if isinstance(data, str):
            text = data.strip()
            if not text:
                raise serializers.ValidationError("Location string is empty.")
            return {"query": text, "source": "address"}

        raise serializers.ValidationError(
            "Location must be a string like 'City, ST' or an object "
            "with 'lat' and 'lon'."
        )

    def to_representation(self, value):
        return value


class RoutePlanRequestSerializer(serializers.Serializer):
    start = LocationField()
    finish = LocationField()

    def validate(self, data):
        # US bounding-box check when coords are supplied directly
        for label in ("start", "finish"):
            loc = data[label]
            if loc.get("source") == "coords":
                lat, lon = loc["lat"], loc["lon"]
                if not (24.0 <= lat <= 49.5 and -125.0 <= lon <= -66.5):
                    raise serializers.ValidationError({
                        label: "Location appears to be outside the continental USA."
                    })
        return data


class LatLonSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lon = serializers.FloatField()


class RouteSerializer(serializers.Serializer):
    distance_miles = serializers.FloatField()
    duration_seconds = serializers.FloatField()
    geometry = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField())
    )
    start = LatLonSerializer()
    finish = LatLonSerializer()


class FuelStopSerializer(serializers.Serializer):
    order = serializers.IntegerField()
    station_id = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    retail_price = serializers.DecimalField(max_digits=8, decimal_places=6)
    distance_from_start_miles = serializers.FloatField()
    gallons_purchased = serializers.DecimalField(max_digits=10, decimal_places=3)
    cost_usd = serializers.DecimalField(max_digits=10, decimal_places=2)


class AssumptionsSerializer(serializers.Serializer):
    vehicle_max_range_miles = serializers.IntegerField()
    fuel_efficiency_mpg = serializers.IntegerField()


class RoutePlanResponseSerializer(serializers.Serializer):
    route = RouteSerializer()
    fuel_stops = FuelStopSerializer(many=True)
    total_fuel_cost_usd = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_gallons_consumed = serializers.DecimalField(max_digits=10, decimal_places=2)
    assumptions = AssumptionsSerializer()