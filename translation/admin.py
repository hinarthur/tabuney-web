# translation/admin.py
from django.contrib import admin
from .models import Tribe, Region, Translation
from .services import apply_usage_scan
import requests
from django.conf import settings
from django import forms
from django.db import models
from django.db.models import F
from django.utils import timezone

@admin.register(Tribe)
class TribeAdmin(admin.ModelAdmin):
    # search_fields = ('name',)
    search_fields = ("name", "language")
    list_display = ('id', 'name', 'language')
    ordering = ('name',)  # 確保 Tribe 列表按 name 排序

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    # 依你 Region model 的欄位調整；我假設是 code/name
    search_fields = ("name", "code")
    list_display = ("name", "code")
    ordering = ("name",)
    

@admin.action(description="🔥同步未sync的到VPS")
def sync_to_vps(modeladmin, request, queryset):
    """
    同步所有 is_synced=False 的 Translation 到 VPS
    不依賴 admin 勾選項目
    """

    qs = Translation.objects.filter(is_synced=False)
    if not qs.exists():
        modeladmin.message_user(
            request,
            "沒有需要同步的翻譯（全部已是最新）"
        )
        return

    translations = []
    for t in qs:
        translations.append({
            'language': t.tribe.language,
            'key': t.key,
            'value': t.value
        })
    _sync_translations_to_vps(modeladmin, request, qs, translations)


@admin.action(description="強行同步已勾選的到VPS（不論 is_synced）")
def force_sync_selected(modeladmin, request, queryset):
    if not queryset.exists():
        modeladmin.message_user(
            request,
            "請先勾選要同步的翻譯項目",
            level='warning'
        )
        return

    translations = []
    for t in queryset:
        translations.append({
            'language': t.tribe.language,
            'key': t.key,
            'value': t.value
        })
    _sync_translations_to_vps(modeladmin, request, queryset, translations)


def _sync_translations_to_vps(modeladmin, request, queryset, translations):
    if not translations:
        modeladmin.message_user(
            request,
            "沒有需要同步的翻譯（全部已是最新）"
        )
        return

    username = settings.VPS_API_USERNAME
    password = settings.VPS_API_PASSWORD

    token_url = 'https://tabuney.com/api/token/'
    sync_url = 'https://tabuney.com/api/translation/sync-translation/'

    try:
        auth_resp = requests.post(
            token_url,
            json={'username': username, 'password': password},
            timeout=(10, 30),
            allow_redirects=False,  # 避免 POST redirect 被自動轉成 GET (RFC 302 行為)
        )

        # 若被 redirect（301/302），直接回報，而非跟隨（跟隨會變 GET）
        if auth_resp.status_code in (301, 302, 307, 308):
            redirect_to = auth_resp.headers.get('Location', '(unknown)')
            modeladmin.message_user(
                request,
                f"登入 VPS 被 redirect ({auth_resp.status_code}) 到 {redirect_to}，請更新 token_url",
                level='error'
            )
            return

        if auth_resp.status_code != 200:
            modeladmin.message_user(
                request,
                f"登入 VPS 失敗 ({auth_resp.status_code}): {auth_resp.text}",
                level='error'
            )
            return

        access_token = auth_resp.json().get('access')
        if not access_token:
            modeladmin.message_user(
                request,
                "登入成功但未取得 access token",
                level='error'
            )
            return

        sync_resp = requests.post(
            sync_url,
            json={'translations': translations},
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            },
            timeout=(10, 120),
        )

        if sync_resp.status_code == 200:
            try:
                sync_data = sync_resp.json()
            except ValueError:
                sync_data = {}

            success = False
            if sync_data.get('result') == 'ok':
                success = True
            elif sync_data.get('count') == len(translations):
                success = True
            elif 'result' not in sync_data:
                success = True

            if success:
                synced_count = queryset.update(
                    is_synced=True,
                    synced_at=timezone.now(),
                )
                modeladmin.message_user(
                    request,
                    f"同步成功，共 {synced_count} 筆翻譯",
                )
            else:
                modeladmin.message_user(
                    request,
                    f"同步失敗 ({sync_resp.status_code}): {sync_resp.text}",
                    level='error'
                )
        else:
            modeladmin.message_user(
                request,
                f"同步失敗 ({sync_resp.status_code}): {sync_resp.text}",
                level='error'
            )

    except requests.exceptions.ReadTimeout:
        modeladmin.message_user(
            request,
            "連線 VPS 時讀取超時，請稍後再試。",
            level='error'
        )
    except requests.exceptions.RequestException as e:
        modeladmin.message_user(
            request,
            f"連線 VPS 發生錯誤: {str(e)}",
            level='error'
        )
    except Exception as e:
        modeladmin.message_user(
            request,
            f"發生未預期錯誤: {str(e)}",
            level='error'
        )


class UntranslatedFilter(admin.SimpleListFilter):
    """value 還是 key 本身 = 自動補上但還沒翻的佔位列。"""
    title = '翻譯狀態'
    parameter_name = 'untranslated'

    def lookups(self, request, model_admin):
        return [('1', '未翻譯 (value=key)')]

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(value=F('key'))
        return queryset


class UnusedFilter(admin.SimpleListFilter):
    """依上一次「掃描使用狀態」action 的結果篩選。"""
    title = '使用狀態'
    parameter_name = 'usage'

    def lookups(self, request, model_admin):
        return [
            ('unused', '未使用 (孤兒 key)'),
            ('unscanned', '尚未掃描過'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'unused':
            return queryset.filter(is_used=False)
        if self.value() == 'unscanned':
            return queryset.filter(is_used__isnull=True)
        return queryset


@admin.action(description="掃描使用狀態（找出孤兒 key）")
def scan_key_usage(modeladmin, request, queryset):
    """手動觸發，跑一次全站掃描，寫回 is_used / used_checked_at。

    故意不掛在 list render 上——掃 template + .py 檔案不是免費的操作，見
    services.py 的說明。
    """
    used_count, unused_count = apply_usage_scan()
    modeladmin.message_user(
        request,
        f"掃描完成：{used_count} 個標記為使用中，{unused_count} 個標記為未使用。"
    )


def _delete_keys_on_vps(modeladmin, request, keys):
    """呼叫 VPS 的刪除 API，成功且刪除筆數與 keys 相符才回傳 True。

    部署順序注意：VPS 若還在跑沒有 action="delete" 分支的舊版 SyncTranslationView，
    舊邏輯會把這個 payload 當成沒有 'translations' 的空同步，直接回 200、什麼都
    沒刪——所以這裡刻意檢查回應裡實際的 deleted 筆數，不能只看 HTTP 200。
    """
    username = settings.VPS_API_USERNAME
    password = settings.VPS_API_PASSWORD
    token_url = 'https://tabuney.com/api/token/'
    delete_url = 'https://tabuney.com/api/translation/sync-translation/'

    try:
        auth_resp = requests.post(
            token_url,
            json={'username': username, 'password': password},
            timeout=(10, 30),
            allow_redirects=False,
        )
        if auth_resp.status_code in (301, 302, 307, 308):
            redirect_to = auth_resp.headers.get('Location', '(unknown)')
            modeladmin.message_user(
                request,
                f"登入 VPS 被 redirect ({auth_resp.status_code}) 到 {redirect_to}",
                level='error'
            )
            return False

        if auth_resp.status_code != 200:
            modeladmin.message_user(
                request,
                f"登入 VPS 失敗 ({auth_resp.status_code}): {auth_resp.text}",
                level='error'
            )
            return False

        access_token = auth_resp.json().get('access')
        if not access_token:
            modeladmin.message_user(request, "登入成功但未取得 access token", level='error')
            return False

        delete_resp = requests.post(
            delete_url,
            json={'action': 'delete', 'keys': keys},
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            },
            timeout=(10, 120),
        )

        if delete_resp.status_code != 200:
            modeladmin.message_user(
                request,
                f"VPS 刪除失敗 ({delete_resp.status_code}): {delete_resp.text}",
                level='error'
            )
            return False

        try:
            delete_data = delete_resp.json()
        except ValueError:
            delete_data = {}

        if delete_data.get('result') != 'ok' or 'deleted' not in delete_data:
            modeladmin.message_user(
                request,
                "VPS 回應格式不含 deleted 筆數，可能是尚未部署刪除功能的舊版本，"
                "為避免資料分歧本次不會刪除本地資料。請先部署 VPS 端改動。",
                level='error'
            )
            return False

        modeladmin.message_user(request, f"VPS 已刪除 {delete_data['deleted']} 筆。")
        return True

    except requests.exceptions.ReadTimeout:
        modeladmin.message_user(request, "連線 VPS 時讀取超時，請稍後再試。", level='error')
        return False
    except requests.exceptions.RequestException as e:
        modeladmin.message_user(request, f"連線 VPS 發生錯誤: {str(e)}", level='error')
        return False
    except Exception as e:
        modeladmin.message_user(request, f"發生未預期錯誤: {str(e)}", level='error')
        return False


@admin.action(description="刪除已勾選的未使用 key（本地 + VPS）")
def delete_unused_and_sync(modeladmin, request, queryset):
    if not queryset.exists():
        modeladmin.message_user(request, "請先勾選要刪除的翻譯項目", level='warning')
        return

    keys = list(queryset.values_list('key', flat=True).distinct())

    # 用勾選到的任何一列所屬的 key，去查該 key 在「所有」語言列的狀態——
    # 刪除是整個 key（所有語言）一起刪，只要有任一列不是確認未使用就整批擋下。
    all_rows_for_keys = Translation.objects.filter(key__in=keys)
    if all_rows_for_keys.filter(is_used__isnull=True).exists() or \
       all_rows_for_keys.filter(is_used=True).exists():
        modeladmin.message_user(
            request,
            "勾選的項目中有尚未掃描過、或已確認使用中的 key，已中止刪除。"
            "請先執行「掃描使用狀態」，只勾選確認為未使用的項目再刪除。",
            level='error'
        )
        return

    if not _delete_keys_on_vps(modeladmin, request, keys):
        return

    deleted_count, _ = all_rows_for_keys.delete()
    modeladmin.message_user(
        request,
        f"本地已刪除 {deleted_count} 筆（共 {len(keys)} 個 key，所有語言）。"
    )


@admin.register(Translation)
class TranslationAdmin(admin.ModelAdmin):
    actions = [sync_to_vps, force_sync_selected, scan_key_usage, delete_unused_and_sync]   # local 專用
    list_display = ('tribe', 'key', 'value', 'is_synced', 'synced_at', 'is_used', 'used_checked_at')   # local 專用
    # list_display = ('tribe', 'key', 'value', )    # VPS 專用
    list_editable = ('key', 'value', )
    list_filter = ('is_synced', 'tribe', UntranslatedFilter, UnusedFilter)   # local 專用
    # list_filter = ('tribe', ) # VPS 專用
    search_fields = ('key', 'value')
    
    # 清單顯示截短的 value
    def short_value(self, obj):
        return obj.value[:50] + '...' if len(obj.value) > 50 else obj.value
    short_value.short_description = 'Value'
    
    # 讓 value 在清單用 textarea
    formfield_overrides = {
        models.TextField: {'widget': forms.Textarea(attrs={'rows': 2, 'cols': 40})},
    }
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "tribe":
            kwargs["queryset"] = Tribe.objects.order_by('name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """新增一個 key 時，自動把其餘 UI 語言補齊，value 先填 key 本身。

        免去每加一句話就要 add 六次的工序。語言清單取自 settings.LANGUAGES
        （en/de/es/fr/ja/zh），不是 Tribe.objects.all() —— DB 裡還有 it/ko/nl/pt
        這些純內容語言的 Tribe，不屬於 UI 翻譯範圍。
        """
        super().save_model(request, obj, form, change)
        if change:
            return

        created = []
        for code, _label in settings.LANGUAGES:
            tribe = Tribe.objects.filter(language=code).first()
            if tribe is None or tribe.pk == obj.tribe_id:
                continue
            # get_or_create 而非 update_or_create：key 若已存在於某語言，
            # 保留既有翻譯，不要被 key 佔位值蓋掉。
            _, was_created = Translation.objects.get_or_create(
                tribe=tribe,
                key=obj.key,
                defaults={'value': obj.key, 'is_synced': False},
            )
            if was_created:
                created.append(code)

        if created:
            self.message_user(
                request,
                f"已自動補上 {len(created)} 個語言（{', '.join(created)}），"
                f"value 暫填 key，記得回來翻譯。"
            )
        
