"""Pure string helpers."""


def clean_whitespace(s: str) -> str:
    """Collapse internal whitespace and strip. Handles the CSV's trailing-space columns."""
    return " ".join((s or "").split())


def normalize_city(city: str) -> str:
    """Canonical form for cache keys and dedup: lowercase, single-spaced."""
    return clean_whitespace(city).lower()