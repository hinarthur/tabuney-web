from django.contrib import admin

from .models import (
    ViewLog, SearchLog, PageVisit, LanguageClick, ErrorLog, ErrorAlertAck, ServerSample,
)

# 統計摘要與排行榜在 admin 首頁（stats/reports.py + templates/admin/index.html），
# 這裡只保留可翻查的原始資料列表。


# =============================
# ViewLog Admin
# =============================
@admin.register(ViewLog)
class ViewLogAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'get_target',
        'member',
        'created_at',
    ]
    list_filter = [
        'content_type',
        'created_at',
    ]
    search_fields = [
        'member__id__username',  # 透過 Member → User 搜尋
    ]
    readonly_fields = [
        'content_type',
        'object_id',
        'member',
        'created_at',
    ]
    list_per_page = 50
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def get_target(self, obj):
        """顯示被瀏覽的對象"""
        try:
            target = obj.content_object
            if target:
                return f"{obj.content_type.model.capitalize()} #{obj.object_id} - {target}"
            return f"{obj.content_type.model.capitalize()} #{obj.object_id} (已刪除)"
        except Exception:
            return f"{obj.content_type.model.capitalize()} #{obj.object_id}"
    get_target.short_description = '瀏覽對象'

    def has_add_permission(self, request):
        """後台不允許手動新增"""
        return False

    def has_change_permission(self, request, obj=None):
        """後台不允許修改"""
        return False


# =============================
# SearchLog Admin
# =============================
@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'keyword',
        'search_type',
        'result_count',
        'matched_by',
        'input_kind',
        'source',
        'lang',
        'is_bot',
        'member',
        'created_at',
    ]
    list_filter = [
        'search_type',
        'source',
        'input_kind',
        'matched_by',
        'is_bot',
        'created_at',
    ]
    search_fields = [
        'keyword',
        'member__id__username',
    ]
    readonly_fields = [
        'keyword',
        'search_type',
        'member',
        'result_count',
        'matched_by',
        'input_kind',
        'source',
        'lang',
        'is_bot',
        'created_at',
    ]
    list_per_page = 50
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# =============================
# PageVisit Admin
# =============================
@admin.register(PageVisit)
class PageVisitAdmin(admin.ModelAdmin):
    list_display = ['page', 'date', 'count']
    list_filter = ['page', 'date']
    ordering = ['-date']
    date_hierarchy = 'date'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# =============================
# LanguageClick Admin
# =============================
@admin.register(LanguageClick)
class LanguageClickAdmin(admin.ModelAdmin):
    list_display = ['kind', 'lang', 'date', 'count']
    list_filter = ['kind', 'lang', 'date']
    ordering = ['-date']
    date_hierarchy = 'date'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# =============================
# ErrorLog Admin
# =============================
class BotFilter(admin.SimpleListFilter):
    """預設只看真人撞到的錯誤；爬蟲/掃描器的 404 佔絕大多數，會蓋掉有用訊號。"""
    title = '來源'
    parameter_name = 'bot'

    def lookups(self, request, model_admin):
        return [('yes', '只看爬蟲'), ('all', '全部')]

    def choices(self, changelist):
        # SimpleListFilter 預設把「全部」綁在無參數上；這裡無參數＝真人，要自己畫
        current = self.value()
        yield {
            'selected': current is None,
            'query_string': changelist.get_query_string(remove=[self.parameter_name]),
            'display': '只看真人（預設）',
        }
        for lookup, title in self.lookup_choices:
            yield {
                'selected': current == lookup,
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(is_bot=True)
        if self.value() == 'all':
            return queryset
        return queryset.filter(is_bot=False)


@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    """
    首頁只顯示排行榜；要追一個特定壞連結、或看爬蟲那一半的資料時來這裡翻。
    """
    list_display = [
        'date',
        'status_code',
        'path',
        'referer',
        'exception',
        'count',
        'member_count',
        'is_bot',
        'last_seen_at',
    ]
    list_filter = [
        'status_code',
        BotFilter,
        'date',
    ]
    search_fields = [
        'path',
        'referer',
        'exception',
    ]
    readonly_fields = [
        'fingerprint',
        'status_code',
        'path',
        'referer',
        'exception',
        'is_bot',
        'date',
        'count',
        'member_count',
        'last_seen_at',
    ]
    list_per_page = 50
    ordering = ['-date', '-count']
    date_hierarchy = 'date'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# =============================
# ErrorAlertAck Admin
# =============================
# 在首頁按錯了「已處理」，到這裡刪掉那一列，警示就會回來
@admin.register(ErrorAlertAck)
class ErrorAlertAckAdmin(admin.ModelAdmin):
    list_display = ['kind', 'path', 'referer', 'acked_at', 'acked_by']
    list_filter = ['kind']
    search_fields = ['path', 'referer']
    readonly_fields = ['key', 'kind', 'path', 'referer', 'acked_at', 'acked_by']


# =============================
# ServerSample Admin
# =============================
@admin.register(ServerSample)
class ServerSampleAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'mem_available_mb', 'mem_total_mb', 'swap_used_mb',
        'load1', 'load5', 'disk_used_pct',
    ]
    date_hierarchy = 'created_at'
    list_per_page = 100
