"""
End-to-end endpoint tests with ORS mocked. No network.
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from core.exceptions import RoutingProviderError
from stations.models import GeocodeCache, Station


NYC = (40.7127, -74.0060)
LA = (34.0522, -118.2437)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def seed_cache(db):
    """NYC + LA available in the geocode cache."""
    GeocodeCache.objects.create(
        query="new york, ny, usa", latitude=NYC[0], longitude=NYC[1],
        provider="static-csv",
    )
    GeocodeCache.objects.create(
        query="los angeles, ca, usa", latitude=LA[0], longitude=LA[1],
        provider="static-csv",
    )

@pytest.fixture
def seed_stations(db, point_on_line):
    """
    Seed stations ON the NYC→LA line so they fall inside the corridor.

    Fractions are spaced 0.10 apart. Even if the interpolated route is
    3000 miles long, the largest gap between consecutive stations is
    ~300 mi — comfortably under the 500-mi vehicle range.
    """
    layout = [
        (0.10, "2.50", "CHEAP 1"),
        (0.20, "2.80", "MID 1"),
        (0.30, "3.00", "MID 2"),
        (0.40, "2.60", "CHEAP 2"),
        (0.50, "3.20", "PRICEY"),
        (0.60, "2.90", "MID 3"),
        (0.70, "2.70", "CHEAP 3"),
        (0.80, "3.10", "MID 4"),
        (0.90, "2.85", "MID 5"),
    ]
    for i, (t, price, name) in enumerate(layout):
        lat, lon = point_on_line(NYC, LA, t)
        Station.objects.create(
            opis_id=str(i + 1),
            name=name,
            city=f"City{i}",
            state="XX",
            retail_price=price,
            latitude=lat,
            longitude=lon,
            geocode_provider="static-csv",
        )


@pytest.mark.django_db
class TestRoutePlanEndpoint:
    URL = "/api/v1/route/plan-fuel-stops/"

    def test_string_input_returns_full_response(
        self, api_client, seed_cache, seed_stations, fake_route_result,
    ):
        fake = fake_route_result(start=NYC, finish=LA)

        with patch("api.views.OpenRouteServiceProvider") as MockProvider:
            MockProvider.return_value.get_route.return_value = fake
            resp = api_client.post(
                self.URL,
                {"start": "New York, NY", "finish": "Los Angeles, CA"},
                format="json",
            )

        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert "route" in data
        assert "fuel_stops" in data
        assert "total_fuel_cost_usd" in data
        assert data["assumptions"]["vehicle_max_range_miles"] == 500
        assert data["assumptions"]["fuel_efficiency_mpg"] == 10
        # Sanity: we should have at least one stop on a 2400+ mi route
        assert len(data["fuel_stops"]) >= 1

    def test_coords_input_works(
        self, api_client, seed_stations, fake_route_result,
    ):
        fake = fake_route_result(start=NYC, finish=LA)

        with patch("api.views.OpenRouteServiceProvider") as MockProvider:
            MockProvider.return_value.get_route.return_value = fake
            resp = api_client.post(
                self.URL,
                {
                    "start": {"lat": NYC[0], "lon": NYC[1]},
                    "finish": {"lat": LA[0], "lon": LA[1]},
                },
                format="json",
            )

        assert resp.status_code == 200, resp.content

    def test_unknown_city_returns_invalid_location(
        self, api_client, seed_cache, seed_stations,
    ):
        resp = api_client.post(
            self.URL,
            {"start": "Zzyzx, CA", "finish": "Los Angeles, CA"},
            format="json",
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "invalid_location"

    def test_bad_request_shape(self, api_client):
        resp = api_client.post(self.URL, {"foo": "bar"}, format="json")
        assert resp.status_code == 400

    def test_ors_failure_returns_provider_error(
        self, api_client, seed_cache, seed_stations,
    ):
        with patch("api.views.OpenRouteServiceProvider") as MockProvider:
            MockProvider.return_value.get_route.side_effect = RoutingProviderError(
                "upstream down"
            )
            resp = api_client.post(
                self.URL,
                {"start": "New York, NY", "finish": "Los Angeles, CA"},
                format="json",
            )

        assert resp.status_code == 502, resp.content
        assert resp.json()["error"]["code"] == "routing_provider_error"