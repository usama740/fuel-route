from django.db import models

class GeocodeCache(models.Model):
    """
    Durable cache of (city, state) -> (lat, lon) lookups.
    Protects the ORS Pelias rate limit and makes the loader re-runnable for free.
    """
    query = models.CharField(max_length=255, unique=True, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    provider = models.CharField(max_length=32, default="ors-pelias")
    confidence = models.FloatField(null=True, blank=True)
    raw_response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stations_geocode_cache"
        verbose_name = "Geocode Cache Entry"
        verbose_name_plural = "Geocode Cache Entries"

    def __str__(self) -> str:
        return f"{self.query} -> ({self.latitude}, {self.longitude})"


class Station(models.Model):
    """
    A fuel station from the OPIS CSV, one row per unique (opis_id, city, state).
    Multiple CSV rows for the same station are collapsed to min(retail_price).
    """
    opis_id = models.CharField(max_length=16, db_index=True)
    name = models.CharField(max_length=128)
    address = models.CharField(max_length=256, blank=True)
    city = models.CharField(max_length=64, db_index=True)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.CharField(max_length=16, blank=True)
    retail_price = models.DecimalField(max_digits=8, decimal_places=6)

    latitude = models.FloatField(null=True, blank=True, db_index=True)
    longitude = models.FloatField(null=True, blank=True, db_index=True)
    geocode_provider = models.CharField(max_length=32, blank=True)
    geocoded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stations_station"
        unique_together = [("opis_id", "city", "state")]
        indexes = [
            models.Index(fields=["state", "city"]),
            models.Index(fields=["latitude", "longitude"]),
        ]
        verbose_name = "Fuel Station"
        verbose_name_plural = "Fuel Stations"

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state}) @ ${self.retail_price}"

    @property
    def is_geocoded(self) -> bool:
        return self.latitude is not None and self.longitude is not None