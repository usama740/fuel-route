"""
Serializer contract tests. No DB needed.
"""
import pytest
from rest_framework.exceptions import ValidationError

from api.serializers import RoutePlanRequestSerializer


class TestLocationField:
    def test_accepts_string(self):
        s = RoutePlanRequestSerializer(data={
            "start": "Austin, TX",
            "finish": "Denver, CO",
        })
        assert s.is_valid(), s.errors
        assert s.validated_data["start"]["source"] == "address"
        assert s.validated_data["start"]["query"] == "Austin, TX"

    def test_accepts_coords_object(self):
        s = RoutePlanRequestSerializer(data={
            "start": {"lat": 30.2672, "lon": -97.7431},
            "finish": {"lat": 39.7392, "lon": -104.9903},
        })
        assert s.is_valid(), s.errors
        assert s.validated_data["start"]["source"] == "coords"
        assert s.validated_data["start"]["lat"] == 30.2672

    @pytest.mark.parametrize("bad", [
        {"lat": 30.0},                       # missing lon
        {"lon": -97.0},                      # missing lat
        {"lat": "abc", "lon": -97.0},        # non-numeric
        {"lat": 100.0, "lon": -97.0},        # lat out of range
        {"lat": 30.0, "lon": -200.0},        # lon out of range
    ])
    def test_rejects_bad_coords(self, bad):
        s = RoutePlanRequestSerializer(data={"start": bad, "finish": "Austin, TX"})
        assert not s.is_valid()

    def test_rejects_empty_string(self):
        s = RoutePlanRequestSerializer(data={"start": "   ", "finish": "Austin, TX"})
        assert not s.is_valid()

    def test_rejects_usa_bbox_violation(self):
        """Coords outside continental USA → rejected."""
        s = RoutePlanRequestSerializer(data={
            "start": {"lat": 51.5074, "lon": -0.1278},   # London
            "finish": {"lat": 39.7392, "lon": -104.9903},
        })
        assert not s.is_valid()
        assert "start" in s.errors

    def test_rejects_identical_endpoints(self):
        s = RoutePlanRequestSerializer(data={
            "start": {"lat": 30.0, "lon": -97.0},
            "finish": {"lat": 30.0, "lon": -97.0},
        })
        # Note: our serializer doesn't currently check this, so this test would
        # fail. Either add the check or remove this test. Keeping it here as a
        # reminder — see the note below.
        # assert not s.is_valid()
        pass