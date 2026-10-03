# stations/tests/test_load_fuel_prices.py
"""
Loader command tests. Uses a small fixture CSV and a pre-seeded GeocodeCache.
"""
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from stations.models import GeocodeCache, Station


FIXTURE_CSV = """OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price
7,WOODSHED OF BIG CABIN,"I-44, EXIT 283 & US-69",Big Cabin,OK,307,3.00733333
7,WOODSHED OF BIG CABIN,"I-44, EXIT 283 & US-69",Big Cabin,OK,307,2.799
7,WOODSHED OF BIG CABIN,"I-44, EXIT 283 & US-69",Big Cabin,OK,307,3.5
9,KWIK TRIP #796,"I-94, EXIT 143",Tomah,WI,420,3.28733333
20,PILOT TRAVEL CENTER #1243,I-8 Gila Bend,Gila Bend,AZ,930,3.899
629,FLYING J #850,TCH-16,Edmonton,AB,80,4.39948962
999,BROKEN ROW,Missing State,,,999,
"""


@pytest.fixture
def fixture_csv(tmp_path):
    p = tmp_path / "fuel.csv"
    p.write_text(FIXTURE_CSV)
    return str(p)


@pytest.fixture
def seed_geocode_cache(db):
    for city, state, lat, lon in [
        ("Big Cabin", "OK", 36.5373, -95.2214),
        ("Tomah", "WI", 43.9786, -90.5040),
        ("Gila Bend", "AZ", 32.9478, -112.7168),
    ]:
        GeocodeCache.objects.create(
            query=f"{city.lower()}, {state.lower()}, usa",
            latitude=lat, longitude=lon, provider="static-csv",
        )


@pytest.mark.django_db
class TestLoadFuelPrices:
    def test_dedups_and_takes_min_price(
        self, fixture_csv, seed_geocode_cache
    ):
        out = StringIO()
        call_command("load_fuel_prices", file=fixture_csv, stdout=out)

        # Big Cabin had 3 rows; kept 1 with min price (2.799)
        stations = Station.objects.filter(city="Big Cabin")
        assert stations.count() == 1
        assert stations.first().retail_price == Decimal("2.799")

        # Total US stations: Big Cabin + Tomah + Gila Bend = 3
        assert Station.objects.count() == 3

    def test_skips_non_us(
        self, fixture_csv, seed_geocode_cache
    ):
        call_command("load_fuel_prices", file=fixture_csv, stdout=StringIO())
        # Edmonton AB was skipped
        assert not Station.objects.filter(state="AB").exists()

    def test_skips_malformed(
        self, fixture_csv, seed_geocode_cache
    ):
        call_command("load_fuel_prices", file=fixture_csv, stdout=StringIO())
        # The "BROKEN ROW" with empty state/city was skipped
        assert not Station.objects.filter(opis_id="999").exists()

    def test_dry_run_writes_nothing(
        self, fixture_csv, seed_geocode_cache
    ):
        call_command(
            "load_fuel_prices", file=fixture_csv, dry_run=True,
            stdout=StringIO(),
        )
        assert Station.objects.count() == 0

    def test_stations_get_coordinates_from_cache(
        self, fixture_csv, seed_geocode_cache
    ):
        call_command("load_fuel_prices", file=fixture_csv, stdout=StringIO())
        big_cabin = Station.objects.get(city="Big Cabin")
        assert big_cabin.latitude is not None
        assert big_cabin.longitude is not None
        assert big_cabin.geocode_provider == "static-csv"

    def test_idempotent_re_run(
        self, fixture_csv, seed_geocode_cache
    ):
        call_command("load_fuel_prices", file=fixture_csv, stdout=StringIO())
        first_count = Station.objects.count()

        call_command("load_fuel_prices", file=fixture_csv, stdout=StringIO())
        assert Station.objects.count() == first_count