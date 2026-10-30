from django.contrib import admin
from .models import Interaction


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ("member", "edition", "rating", "status", "created_at", "updated_at")
    list_filter = ("rating", "status", "created_at")
    search_fields = ("member__id__username", "edition__name")
    raw_id_fields = ("member", "edition")
