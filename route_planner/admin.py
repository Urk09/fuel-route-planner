from django.contrib import admin

from .models import FuelStation

@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("opis_id", "name", "city", "state", "retail_price", "updated_at")
    list_filter = ("state",)
    search_fields = ("name", "city")
    ordering = ("retail_price",)