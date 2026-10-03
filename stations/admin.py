# stations/admin.py
from django.contrib import admin
from .models import Station, GeocodeCache


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "retail_price", "latitude", "longitude")
    list_filter = ("state",)
    search_fields = ("name", "city", "opis_id")
    readonly_fields = ("created_at", "updated_at", "geocoded_at")


@admin.register(GeocodeCache)
class GeocodeCacheAdmin(admin.ModelAdmin):
    list_display = ("query", "latitude", "longitude", "provider", "created_at")
    search_fields = ("query",)