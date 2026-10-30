from django.contrib import admin
from .models import Affiliate, Artwork, AdClick, CallToAction

@admin.register(Artwork)
class ArtworkAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at')
    search_fields = ('title', 'prompt')

@admin.register(Affiliate)
class AffiliateAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'cta_name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'url', 'search_key', 'cta_name')
    actions = ['sync_to_vps']

    @admin.action(description="Sync selected to VPS")
    def sync_to_vps(self, request, queryset):
        from game.sync_service import GameSyncService
        from django.contrib import messages
        
        service = GameSyncService()
        sync_log = service.sync_affiliates(queryset)
        
        if sync_log.status == 'success':
            messages.success(request, f"Successfully synced {sync_log.records_sent} records and {sync_log.media_sent} files to VPS.")
        elif sync_log.status == 'partial':
            messages.warning(request, f"Partial sync: {sync_log.error_message}")
        else:
            messages.error(request, f"Sync failed: {sync_log.error_message}")

@admin.register(CallToAction)
class CallToActionAdmin(admin.ModelAdmin):
    list_display = ('name', 'text', 'tribe', 'created_at')
    list_filter = ('tribe',)
    search_fields = ('name', 'text')
    autocomplete_fields = ('tribe',)

@admin.register(AdClick)
class AdClickAdmin(admin.ModelAdmin):
    list_display = ('affiliate', 'created_at', 'referer')
    list_filter = ('created_at', 'affiliate')
    readonly_fields = ('created_at', 'updated_at', 'affiliate', 'referer')
