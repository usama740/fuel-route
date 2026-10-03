"""
Projects geocoded stations onto a route polyline.

Strategy:
  1. Build a KD-tree over route vertices (fast lookup).
  2. For each station, find its nearest route vertex.
  3. Check the two segments adjacent to that vertex for perpendicular projection.
  4. Return the best (distance_along, distance_off) across both.

Complexity: O(N log M + K) where N = stations, M = route vertices, K = candidates.
"""
from typing import List, Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree

from core.utils.geo import haversine_miles


class RouteProjector:
    def __init__(self, route_coords: List[Tuple[float, float]]):
        """
        route_coords: [(lat, lon), ...] in order along the route.
        """
        if len(route_coords) < 2:
            raise ValueError("Route needs at least 2 coordinates.")

        self._coords = np.asarray(route_coords, dtype=np.float64)  # (N, 2) [lat, lon]

        # Cumulative distance from start to each vertex, in miles
        self._cum = np.zeros(len(route_coords), dtype=np.float64)
        for i in range(1, len(route_coords)):
            lat1, lon1 = route_coords[i - 1]
            lat2, lon2 = route_coords[i]
            self._cum[i] = self._cum[i - 1] + haversine_miles(lat1, lon1, lat2, lon2)

        self.total_distance_miles = float(self._cum[-1])

        # KD-tree over route vertices (lat/lon 2D). Adequate for finding the
        # nearest vertex; exact distance is then computed via haversine.
        self._tree = cKDTree(self._coords)

    # ------------------------------------------------------------------
    def project(self, lat: float, lon: float) -> Tuple[float, float]:
        """
        Return (distance_along_route, distance_off_route) in miles
        for the given point relative to the route polyline.
        """
        # Find the nearest route vertex (and 2 neighbors for safety)
        _, idx = self._tree.query([lat, lon], k=min(3, len(self._coords)))
        candidates = {int(idx)} if np.isscalar(idx) else set(int(i) for i in idx)

        best_along = 0.0
        best_off = float("inf")

        for vertex_idx in candidates:
            # Consider segments (vertex_idx-1, vertex_idx) and (vertex_idx, vertex_idx+1)
            for seg_start in (vertex_idx - 1, vertex_idx):
                if seg_start < 0 or seg_start + 1 >= len(self._coords):
                    continue
                along, off = self._project_on_segment(seg_start, lat, lon)
                if off < best_off:
                    best_off = off
                    best_along = along

        return best_along, best_off

    # ------------------------------------------------------------------
    def _project_on_segment(self, seg_idx: int, lat: float, lon: float) -> Tuple[float, float]:
        """
        Project point onto segment from route_coords[seg_idx] to route_coords[seg_idx+1].
        Returns (distance_along_route_to_projection, perpendicular_distance_miles).
        """
        a_lat, a_lon = self._coords[seg_idx]
        b_lat, b_lon = self._coords[seg_idx + 1]

        # Work in local planar approximation around the segment.
        # 1 degree lat ~ 69.0 mi; 1 degree lon ~ 69.0 * cos(lat) mi.
        cos_lat = np.cos(np.radians((a_lat + b_lat) / 2.0))
        ax, ay = 0.0, 0.0
        bx = (b_lon - a_lon) * cos_lat * 69.0
        by = (b_lat - a_lat) * 69.0
        px = (lon - a_lon) * cos_lat * 69.0
        py = (lat - a_lat) * 69.0

        seg_len_sq = bx * bx + by * by
        if seg_len_sq < 1e-12:
            # Degenerate segment
            t = 0.0
        else:
            t = (px * bx + py * by) / seg_len_sq
            t = max(0.0, min(1.0, t))

        proj_x = t * bx
        proj_y = t * by
        off = float(np.hypot(px - proj_x, py - proj_y))

        # Exact haversine distance for accuracy
        proj_lat = a_lat + t * (b_lat - a_lat)
        proj_lon = a_lon + t * (b_lon - a_lon)
        segment_miles = haversine_miles(a_lat, a_lon, b_lat, b_lon)
        along = float(self._cum[seg_idx] + t * segment_miles)

        return along, off