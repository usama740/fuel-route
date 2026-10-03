"""
Lazy singleton over all geocoded stations. Built on first request, held for
the life of the process. Zero API calls, zero per-request DB queries.
"""
import logging
import threading
from typing import List

from django.db import connection

from stations.models import Station

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_instance = None


class StationIndex:
    def __init__(self, stations: List[Station]):
        self._stations = stations

    def all_stations(self) -> List[Station]:
        return self._stations

    def __len__(self) -> int:
        return len(self._stations)


def get_station_index() -> StationIndex:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                logger.info("Building station index from DB...")
                qs = Station.objects.exclude(latitude=None).exclude(longitude=None).only(
                    "id", "name", "city", "state", "latitude", "longitude",
                    "retail_price",
                )
                _instance = StationIndex(list(qs))
                logger.info("Station index built: %d stations", len(_instance))
    return _instance


def invalidate_station_index() -> None:
    """Call after re-running the loader to force a rebuild."""
    global _instance
    with _lock:
        _instance = None