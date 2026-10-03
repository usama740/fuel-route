"""
Location string -> (lat, lon) resolver.

Strategy (in order):
  1. Parse "City, ST" (2-letter state required)
  2. Exact lookup in local GeocodeCache
  3. Alias lookup (well-known alternate spellings)
  4. Fuzzy fallback (startswith / icontains)
  5. Raise InvalidLocationError with a helpful message
"""
import logging
import re
from typing import List, Optional, Tuple

from django.db.models import Q

from core.exceptions import InvalidLocationError
from core.utils.text import clean_whitespace
from stations.models import GeocodeCache

logger = logging.getLogger(__name__)


_CITY_STATE_RE = re.compile(r"^\s*(.+?)\s*,\s*([A-Za-z]{2})\s*$")


# Well-known aliases: what users type -> what the CSV stores.
# Keys are (normalized_city.lower(), STATE.upper()).
ALIASES = {
    ("new york", "NY"): "new york city",
    ("nyc", "NY"): "new york city",
    ("washington", "DC"): "washington",
    ("d.c.", "DC"): "washington",
    ("dc", "DC"): "washington",
    ("st louis", "MO"): "saint louis",
    ("st. louis", "MO"): "saint louis",
    ("st paul", "MN"): "saint paul",
    ("st. paul", "MN"): "saint paul",
    ("st petersburg", "FL"): "saint petersburg",
    ("st. petersburg", "FL"): "saint petersburg",
    ("ft worth", "TX"): "fort worth",
    ("ft. worth", "TX"): "fort worth",
    ("ft lauderdale", "FL"): "fort lauderdale",
    ("ft. lauderdale", "FL"): "fort lauderdale",
    ("ft wayne", "IN"): "fort wayne",
    ("ft. wayne", "IN"): "fort wayne",
    ("las vegas", "NV"): "las vegas",
    ("la", "CA"): "los angeles",
    ("sf", "CA"): "san francisco",
    ("philly", "PA"): "philadelphia",
}


class LocationResolver:
    """Resolves 'City, ST' strings using the local GeocodeCache."""

    def resolve(self, query: str) -> Tuple[float, float]:
        city, state = self._parse(query)

        # 1. Exact match
        key = self._cache_key(city, state)
        hit = GeocodeCache.objects.filter(query=key).first()
        if hit is not None:
            return hit.latitude, hit.longitude

        # 2. Alias table
        alias_city = ALIASES.get((city.lower(), state))
        if alias_city:
            alias_key = self._cache_key(alias_city, state)
            hit = GeocodeCache.objects.filter(query=alias_key).first()
            if hit is not None:
                return hit.latitude, hit.longitude

        # 3. Fuzzy fallback — city name starts with what the user typed
        #    (handles "new york" -> "new york city", "kansas" -> "kansas city", etc.)
        candidate = (
            GeocodeCache.objects
            .filter(query__startswith=f"{city.lower()}, {state.lower()}, usa")
            .first()
        )
        if candidate is None:
            # Broader: contains the typed city, exact state
            candidate = (
                GeocodeCache.objects
                .filter(query__icontains=f"{city.lower()},")
                .filter(query__endswith=f"{state.lower()}, usa")
                .order_by("query")   # deterministic pick
                .first()
            )

        if candidate is not None:
            logger.info(
                "Fuzzy geocode: '%s, %s' -> cache key %r",
                city, state, candidate.query,
            )
            return candidate.latitude, candidate.longitude

        raise InvalidLocationError(
            f"Could not resolve '{query}'. Use format 'City, ST' "
            f"(e.g. 'Austin, TX') or supply lat/lon directly."
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _cache_key(city: str, state: str) -> str:
        return f"{city.strip().lower()}, {state.strip().lower()}, usa"

    @staticmethod
    def _parse(query: str) -> Tuple[str, str]:
        text = clean_whitespace(query)
        m = _CITY_STATE_RE.match(text)
        if not m:
            raise InvalidLocationError(
                f"Could not parse '{query}'. Expected 'City, ST' "
                f"(e.g. 'Austin, TX')."
            )
        city = clean_whitespace(m.group(1))
        state = m.group(2).upper()
        if not city:
            raise InvalidLocationError(f"Missing city in '{query}'.")
        return city, state