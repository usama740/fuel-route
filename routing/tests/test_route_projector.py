"""
Unit tests for the route projector.

Uses a simple straight-line polyline so distances are analytically known.
"""
import pytest

from routing.services.route_projector import RouteProjector
from core.utils.geo import haversine_miles


class TestStraightLineProjection:
    @pytest.fixture
    def west_east_route(self):
        """
        Straight line along lat=40, from lon=-100 to lon=-90.
        Roughly 530 miles long (1 deg lon at lat 40 ≈ 53 mi).
        """
        return [(-100.0 + 0.1 * i, 40.0) for i in range(101)]  # lon in [-100, -90]

    def test_projector_raises_on_short_route(self):
        with pytest.raises(ValueError):
            RouteProjector([(0.0, 0.0)])

    def test_total_distance_is_known(self, west_east_route):
        # Build with (lat, lon) order
        coords = [(lat, lon) for lon, lat in west_east_route]
        proj = RouteProjector(coords)
        # 10 degrees of longitude at lat 40 ~ 530 miles
        assert 520 < proj.total_distance_miles < 540

    def test_station_on_route_has_zero_offset(self):
        # Simple route: 3 points along lat=40
        coords = [(40.0, -100.0), (40.0, -95.0), (40.0, -90.0)]
        proj = RouteProjector(coords)

        # Project a point directly on the line
        along, off = proj.project(40.0, -97.5)
        assert off < 0.5                        # ~0 mi off route
        assert 0 < along < proj.total_distance_miles

    def test_station_off_route_has_correct_offset(self):
        coords = [(40.0, -100.0), (40.0, -90.0)]
        proj = RouteProjector(coords)

        # 0.1 degree north of the route (~6.9 mi)
        along, off = proj.project(40.1, -95.0)
        assert 6.5 < off < 7.3
        # Should land at midpoint, ~halfway along
        assert 0.4 * proj.total_distance_miles < along < 0.6 * proj.total_distance_miles

    def test_station_before_start_projects_to_start(self):
        coords = [(40.0, -100.0), (40.0, -90.0)]
        proj = RouteProjector(coords)

        # 0.5 deg west of start
        along, off = proj.project(40.0, -100.5)
        assert along == pytest.approx(0.0, abs=0.5)
        assert off > 20  # ~26 mi west

    def test_station_after_finish_projects_to_finish(self):
        coords = [(40.0, -100.0), (40.0, -90.0)]
        proj = RouteProjector(coords)

        # 0.5 deg east of finish
        along, off = proj.project(40.0, -89.5)
        assert along == pytest.approx(proj.total_distance_miles, abs=1.0)
        assert off > 20