"""
Load US city coordinates from a static world-cities CSV into GeocodeCache.

The source CSV (joelacus/world-cities) has columns:
    country,state,name,lat,lng
For US rows, `state` is the FULL name ("Alabama"), so we normalize
to 2-letter codes to match the rest of our schema.

Usage:
    python manage.py load_static_cities --file data/reference/us_cities.csv
"""
import csv
from pathlib import Path
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.constants import US_STATES
from stations.models import GeocodeCache


# Full state name -> 2-letter code. Covers 50 states + DC.
STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "washington dc": "DC", "washington, d.c.": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def normalize_state(raw: str) -> Optional[str]:
    """
    Accept either a 2-letter code ('GA') or a full name ('Georgia').
    Returns the 2-letter code, or None if unrecognized.
    """
    if not raw:
        return None
    cleaned = raw.strip()
    upper = cleaned.upper()
    if upper in US_STATES:
        return upper
    return STATE_NAME_TO_CODE.get(cleaned.lower())


class Command(BaseCommand):
    help = "Load US city coordinates from a static CSV into the GeocodeCache table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            required=True,
            help="Path to the world-cities CSV file.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["file"]).resolve()
        if not csv_path.exists():
            raise CommandError(f"File not found: {csv_path}")

        self.stdout.write(f"Loading city coordinates from {csv_path}...")

        entries_to_create = []
        skipped_non_us = 0
        skipped_unrecognized = 0
        skipped_malformed = 0

        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                country = (row.get("country") or "").strip().upper()
                if country not in ("US", "USA", "UNITED STATES"):
                    skipped_non_us += 1
                    continue

                state = normalize_state(row.get("state") or "")
                if state is None:
                    skipped_unrecognized += 1
                    continue

                city = (row.get("name") or "").strip()
                lat_raw = (row.get("lat") or "").strip()
                lng_raw = (row.get("lng") or "").strip()
                if not city or not lat_raw or not lng_raw:
                    skipped_malformed += 1
                    continue

                try:
                    lat = float(lat_raw)
                    lng = float(lng_raw)
                except ValueError:
                    skipped_malformed += 1
                    continue

                cache_key = f"{city.lower()}, {state.lower()}, usa"
                entries_to_create.append(
                    GeocodeCache(
                        query=cache_key,
                        latitude=lat,
                        longitude=lng,
                        provider="static-csv",
                    )
                )

        self.stdout.write(
            f"Scanned CSV: {len(entries_to_create)} US city entries ready, "
            f"skipped {skipped_non_us} non-US, "
            f"{skipped_unrecognized} unrecognized states, "
            f"{skipped_malformed} malformed."
        )

        if not entries_to_create:
            self.stdout.write(self.style.WARNING(
                "No valid entries found. Check the file with: "
                "grep '^US,' <file> | head"
            ))
            return

        # Deduplicate by query key — same (city, state) can appear multiple times.
        deduped = {entry.query: entry for entry in entries_to_create}
        self.stdout.write(
            f"Deduplicated to {len(deduped)} unique (city, state) entries."
        )

        with transaction.atomic():
            GeocodeCache.objects.bulk_create(
                list(deduped.values()),
                ignore_conflicts=True,
                batch_size=1000,
            )

        self.stdout.write(self.style.SUCCESS(
            f"Successfully loaded entries. "
            f"Total in cache now: {GeocodeCache.objects.count()}."
        ))