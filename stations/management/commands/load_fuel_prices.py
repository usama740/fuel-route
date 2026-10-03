"""
Load fuel stations from the OPIS CSV into the DB, looking up coordinates
from the local GeocodeCache table (populated by load_static_cities).

No external API calls are made by this command.

Usage:
    python manage.py load_fuel_prices --file data/fuel-prices-for-be-assessment.csv
    python manage.py load_fuel_prices --file ... --dry-run
"""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.constants import US_STATES, CANADIAN_PROVINCES
from stations.models import GeocodeCache, Station


class Command(BaseCommand):
    help = "Load fuel stations from the OPIS CSV using pre-loaded city coordinates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            required=True,
            help="Path to the fuel prices CSV.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report, do not write to DB.",
        )

    def handle(self, *args, **opts):
        csv_path = Path(opts["file"]).resolve()
        if not csv_path.exists():
            raise CommandError(f"File not found: {csv_path}")

        dry_run = opts["dry_run"]

        # 1. Parse CSV
        raw_rows, skipped_non_us, skipped_malformed = self._parse_csv(csv_path)
        self.stdout.write(
            f"Parsed {len(raw_rows)} valid US rows "
            f"(skipped {skipped_non_us} non-US, "
            f"{skipped_malformed} malformed)."
        )

        # 2. Collapse duplicates by (opis_id, city, state) keeping min price
        stations = self._collapse_duplicates(raw_rows)
        self.stdout.write(f"Collapsed to {len(stations)} unique stations.")

        # 3. Resolve coordinates from local cache (no API calls)
        coords_map, cache_hits = self._resolve_coordinates(stations)
        self.stdout.write(
            f"Resolved {cache_hits} of {len({(s['city'], s['state']) for s in stations.values()})} "
            f"unique (city, state) pairs from cache."
        )

        # 4. Persist
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run: no DB writes performed."))
            return

        created, updated = self._persist(stations, coords_map)
        self.stdout.write(self.style.SUCCESS(
            f"Done. Stations created={created}, updated={updated}."
        ))

    # ------------------------------------------------------------------
    def _parse_csv(self, path: Path):
        rows, skipped_non_us, skipped_malformed = [], 0, 0
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                state = (row.get("State") or "").strip().upper()
                city = " ".join((row.get("City") or "").split())
                name = " ".join((row.get("Truckstop Name") or "").split())
                price_raw = (row.get("Retail Price") or "").strip()
                opis_id = (row.get("OPIS Truckstop ID") or "").strip()

                if not city or not state or not name or not opis_id or not price_raw:
                    skipped_malformed += 1
                    continue
                if state in CANADIAN_PROVINCES or state not in US_STATES:
                    skipped_non_us += 1
                    continue

                try:
                    price = Decimal(price_raw)
                except InvalidOperation:
                    skipped_malformed += 1
                    continue

                rows.append({
                    "opis_id": opis_id,
                    "name": name,
                    "address": " ".join((row.get("Address") or "").split()),
                    "city": city,
                    "state": state,
                    "rack_id": (row.get("Rack ID") or "").strip(),
                    "retail_price": price,
                })
        return rows, skipped_non_us, skipped_malformed

    # ------------------------------------------------------------------
    @staticmethod
    def _collapse_duplicates(rows):
        agg: Dict[Tuple[str, str, str], dict] = {}
        for r in rows:
            key = (r["opis_id"], r["city"], r["state"])
            if key not in agg or r["retail_price"] < agg[key]["retail_price"]:
                agg[key] = r
        return agg

    # ------------------------------------------------------------------
    @staticmethod
    def _cache_key(city: str, state: str) -> str:
        return f"{city.strip().lower()}, {state.strip().lower()}, usa"

    def _resolve_coordinates(self, stations):
        unique_cities = {(s["city"], s["state"]) for s in stations.values()}
        keys = [self._cache_key(c, s) for c, s in unique_cities]

        cache_entries = GeocodeCache.objects.filter(query__in=keys)
        cache_lookup = {e.query: (e.latitude, e.longitude) for e in cache_entries}

        coords_map: Dict[Tuple[str, str], Tuple[float, float]] = {}
        for city, state in unique_cities:
            key = self._cache_key(city, state)
            if key in cache_lookup:
                coords_map[(city, state)] = cache_lookup[key]

        return coords_map, len(coords_map)

    # ------------------------------------------------------------------
    def _persist(self, stations, coords_map):
        created = updated = 0
        now = timezone.now()
        with transaction.atomic():
            for (opis_id, city, state), data in stations.items():
                coords = coords_map.get((city, state))
                defaults = {
                    "name": data["name"],
                    "address": data["address"],
                    "rack_id": data["rack_id"],
                    "retail_price": data["retail_price"],
                }
                if coords:
                    defaults.update(
                        latitude=coords[0],
                        longitude=coords[1],
                        geocode_provider="static-csv",
                        geocoded_at=now,
                    )
                _, was_created = Station.objects.update_or_create(
                    opis_id=opis_id,
                    city=city,
                    state=state,
                    defaults=defaults,
                )
                created += int(was_created)
                updated += int(not was_created)
        return created, updated