"""
Pure helpers only. Rules for adding to this package:
  1. No imports from Django, DRF, or any project app.
  2. No I/O — no DB, no HTTP, no file access.
  3. No global mutable state.
  4. Every function must be testable with plain Python values.

If what you're adding needs any of the above, it belongs in a service
(core/interfaces + a concrete impl) — not here.
"""
from .geo import haversine_miles
from .rate_limit import Throttle
from .text import clean_whitespace, normalize_city

__all__ = ["haversine_miles", "Throttle", "clean_whitespace", "normalize_city"]