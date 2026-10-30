# game/admin.py
import logging
from django.contrib import admin, messages
from django.contrib.admin.views.autocomplete import AutocompleteJsonView
from django.contrib.admin.widgets import AutocompleteSelect, AutocompleteSelectMultiple
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.template.response import TemplateResponse
from django import forms
from django.db import models, transaction
from django.http import JsonResponse
from django.utils import timezone

from .models import (
    Entity, EditionRole,
    Game, GameTitle, Dimension,
    Edition, Component,
    Rulebook,
    RulebookQA,
    RulebookNode,
    RulebookFlowchart,
    FlowchartReview,
    FlowchartTextTranslation,
    RulebookScript,
)
from .models import COMPONENT_MATERIAL_CHOICES, COMPONENT_TYPE_CHOICES, READING_DENSITY_CHOICES
from .rag.constants import GEMINI_MAIN_MODEL  # 純常數模組，無重型依賴
# 注意：rulebook_processing（PyMuPDF/OCR）、ingest 等重型模組改為各 action 內 lazy import，
# 避免 production Django 啟動時就載入 torch/paddleocr 等只在 local 需要的套件。
import re
from collections import Counter
from django import forms
from django.urls import path, reverse
from django.conf import settings
from django.shortcuts import render, redirect
from qdrant_client.models import Filter, FieldCondition, MatchValue
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
import json
import os
import requests as http_requests
from django.core.files.base import ContentFile
from django_q.tasks import async_task

from .models import ChatSession, ChatMessage, Collection, ScrapeLog, ScrapedProduct, GameSuggestion, GameSuggestionStatus, FlowchartSuggestion
from .models import EditionImportQueue
from .sync_models import GameSyncLog
from translation.models import Tribe
import tiktoken

logger = logging.getLogger(__name__)

# ─────────────────────────────
# 環境防呆：重型功能僅限 local 開發環境
# ─────────────────────────────
def _block_heavy_in_production(request) -> bool:
    """重型功能（PDF 擷取 / OCR / RAG ingest / 商品爬蟲 / 產生譯文）僅限 local 開發環境。
    在 production（base requirements 未安裝 PyMuPDF/paddleocr/torch/cloudscraper 等）顯示提示並阻止。
    回傳 True 表示已阻止，呼叫端應立即 return。"""
    if getattr(settings, "DJANGO_ENV", "development") == "production":
        messages.error(request, "⚠️ 此功能僅限開發環境（local）執行；production 未安裝相關套件。")
        return True
    return False


# ─────────────────────────────
# Forms
# ─────────────────────────────

class EntityAdminForm(forms.ModelForm):
    entity_type = forms.ChoiceField(
        choices=(
            ('individual', '個人'),
            ('company', '公司'),
            ('team', '團隊'),
        ),
        required=True,
        label='Entity Type'
    )
    
    class Meta:
        model = Entity
        fields = '__all__'

# ─────────────────────────────
# Inlines
# ─────────────────────────────

class GameTitleInline(admin.TabularInline):
    model = GameTitle
    extra = 1
    autocomplete_fields = ("language",)


class DimensionInline(admin.StackedInline):
    model = Dimension
    extra = 0
    fields = (
        "adaptability", "collaboration", "communication",
        "creativity", "critical_thinking", "problem_solving", "basic",
        "source_member",
    )


class EditionInline(admin.TabularInline):
    model = Edition
    extra = 0
    show_change_link = True

    autocomplete_fields = ("language", "region", "based_on")
    fields = (
        "name", "language", "region",
        "barcode", "release_year", "is_primary",
    )

class EditionRoleInline(admin.TabularInline):
    model = EditionRole
    extra = 1
    autocomplete_fields = ("entity",)


class EntityEditionRoleInline(admin.TabularInline):
    model = EditionRole
    extra = 1
    autocomplete_fields = ("edition",)


class RulebookInline(admin.TabularInline):
    model = Rulebook
    extra = 0
    show_change_link = True

    autocomplete_fields = ("language",)
    fields = (
        "title", "language",
        "status",
    )
    # title 唯讀：這頁若開著沒重整，formset 會把畫面上過時的 title 整批寫回，
    # 蓋掉期間在 Rulebook 編輯頁改好的名字（2026-09-01 Pandemic 16 本就是這樣被還原成
    # 「Pandemic Rulebook (EN)」）。要改 title 請點右側 change link 進 Rulebook 編輯頁。
    readonly_fields = ("title",)


class ComponentInline(admin.TabularInline):
    model = Component
    extra = 1
    fields = ("name", "component_type", "material", "quantity", "description")
    verbose_name = "Component"
    verbose_name_plural = "Components"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Inject choices for component_type and material without adding them to the model."""
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "component_type":
            field.widget = forms.Select(
                choices=[("" , "---------")] + list(COMPONENT_TYPE_CHOICES)
            )
        elif db_field.name == "material":
            field.widget = forms.Select(
                choices=[("" , "---------")] + list(COMPONENT_MATERIAL_CHOICES)
            )
        elif db_field.name == "description":
            field.widget = forms.TextInput(attrs={'style': 'width: 250px;'})
        return field


# ─────────────────────────────
# Admins
# ─────────────────────────────

@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    form = EntityAdminForm
    list_display = ("name", "website", "entity_type", "scraper_name", "last_scraped_at", "created_at", "updated_at")
    list_editable = ("entity_type", )
    list_filter = ("entity_type", "scraper_name")
    search_fields = ("name", "scraper_name")
    ordering = ("name",)
    inlines = (EntityEditionRoleInline,)
    actions = ["run_scraper", "run_scraper_limit_5"]
    formfield_overrides = {
        models.TextField: {'widget': forms.TextInput(attrs={'size': '60'})},
    }
    fieldsets = (
        (None, {
            "fields": ("name", "website", "entity_type",
            "scrape_page_start", "scrape_batch_size",)
        }),
        ("爬蟲設定", {
            "fields": (
                "scraper_name", "last_scraped_at", 
                "scraper_cookie", "scraper_user_agent",
            ),
            # "classes": ("collapse",),
        }),
    )
    readonly_fields = ("last_scraped_at",)

    @admin.action(description="執行爬蟲擷取資料")
    def run_scraper(self, request, queryset):
        self._do_run_scraper(request, queryset)

    @admin.action(description="執行爬蟲擷取資料 (僅 5 筆用於測試)")
    def run_scraper_limit_5(self, request, queryset):
        self._do_run_scraper(request, queryset, limit=5)

    def _do_run_scraper(self, request, queryset, limit=None):
        if _block_heavy_in_production(request):
            return
        import importlib
        from game.models import ScrapeLog, ScrapedProduct
        from django.utils import timezone
        
        for entity in queryset:
            if not entity.scraper_name:
                self.message_user(request, f"Entity {entity.name} 未設定 scraper_name。", level=messages.WARNING)
                continue
                
            try:
                module_name = f"game.scrapers.{entity.scraper_name}"
                scraper_module = importlib.import_module(module_name)
                
                ScraperClass = None
                for attr_name in dir(scraper_module):
                    attr = getattr(scraper_module, attr_name)
                    if isinstance(attr, type) and attr.__name__ != "BaseScraper" and hasattr(attr, "fetch_items"):
                        ScraperClass = attr
                        break
                        
                if not ScraperClass:
                    self.message_user(request, f"在模組 {module_name} 找不到合法的 Scraper Class", level=messages.ERROR)
                    continue
                
                # 處理 batch_size，0 或 None 都視為「不限制頁數」(傳遞 None 給爬蟲)
                batch_size = entity.scrape_batch_size
                if not batch_size:  # 涵蓋 0 和 None
                    batch_size = None
                    
                scraper_instance = ScraperClass(
                    cookie_str=entity.scraper_cookie or "",
                    user_agent=entity.scraper_user_agent or "",
                    # start_page=entity.scrape_page_start or 1,
                    # batch_size=entity.scrape_batch_size or 10,
                    # start_page=entity.scrape_page_start if entity.scrape_page_start is not None else 1,
                    # batch_size=entity.scrape_batch_size if entity.scrape_batch_size is not None else 10,
                    start_page=entity.scrape_page_start or 1,
                    batch_size=batch_size,  # 將 None 傳進去
                )
                
                trigger_member = getattr(request.user, 'member', None) if getattr(request, 'user', None) and request.user.is_authenticated else None
                scrape_log = ScrapeLog.objects.create(
                    publisher=entity,
                    triggered_by=trigger_member,
                    start_at=timezone.now()
                )
                
                items = scraper_instance.run(limit=limit)
                
                # ====== 通用 upsert 邏輯（相容所有 source） ======
                
                def get_lookup_key(raw_data, normalized_data):
                    """
                    通用的 lookup key 取得方法：
                    - 有 bgg_id → 用 "bgg:224517" 格式
                    - 否則 fallback 到 URL
                    確保不同 source 的 key 不會撞
                    """
                    if raw_data and isinstance(raw_data, dict):
                        bgg_id = raw_data.get("bgg_id")
                        if bgg_id is not None:
                            return f"bgg:{bgg_id}"
                    if normalized_data and isinstance(normalized_data, dict):
                        url = normalized_data.get("url")
                        if url:
                            return f"url:{url}"
                    return None
                
                # 建立該 entity 既有產品的 key → ScrapedProduct 對照表
                existing_products = {}
                for sp in ScrapedProduct.objects.filter(scrapelog__publisher=entity):
                    key = get_lookup_key(sp.raw_data, sp.normalized_data)
                    if key:
                        existing_products[key] = sp
                
                created_count = 0
                updated_count = 0
                skipped_count = 0
                
                for item in items:
                    norm_data = item.to_normalized_dict()
                    raw_data = item.raw_data
                    key = get_lookup_key(raw_data, norm_data)
                    
                    if key and key in existing_products:
                        existing = existing_products[key]
                        # 已審核（匯入或拒絕）→ 不覆蓋
                        if existing.status in (ScrapedProduct.Status.IMPORTED, ScrapedProduct.Status.REJECTED):
                            skipped_count += 1
                            continue
                        # PENDING + 完全相同 → 跳過
                        if (existing.normalized_data == norm_data and 
                            existing.raw_data == raw_data and
                            existing.rank == norm_data.get('rank') and
                            existing.family_rank == norm_data.get('family_rank') and
                            existing.party_rank == norm_data.get('party_rank')):
                            skipped_count += 1
                            continue
                        # PENDING + 有變 → 更新（status 維持 PENDING）
                        existing.scrapelog = scrape_log
                        existing.raw_data = raw_data
                        existing.normalized_data = norm_data
                        existing.rank = norm_data.get('rank')
                        existing.family_rank = norm_data.get('family_rank')
                        existing.party_rank = norm_data.get('party_rank')
                        existing.save(update_fields=[
                            "scrapelog", "raw_data", "normalized_data", 
                            "rank", "family_rank", "party_rank", "updated_at"
                        ])
                        updated_count += 1
                    else:
                        # 新產品
                        ScrapedProduct.objects.create(
                            scrapelog=scrape_log,
                            raw_data=raw_data,
                            normalized_data=norm_data,
                            status=ScrapedProduct.Status.PENDING,
                            rank=norm_data.get('rank'),
                            family_rank=norm_data.get('family_rank'),
                            party_rank=norm_data.get('party_rank'),
                        )
                        created_count += 1
                
                # ====== upsert 結束 ======
                
                scrape_log.finish_at = timezone.now()
                scrape_log.qty = created_count + updated_count
                scrape_log.save(update_fields=["finish_at", "qty"])
                
                entity.last_scraped_at = timezone.now()
                entity.save(update_fields=["last_scraped_at", "updated_at"])
                
                limit_suffix = f" (限制 {limit} 筆)" if limit else ""
                self.message_user(
                    request,
                    f"✅ {entity.name}{limit_suffix}："
                    f"新增 {created_count}，更新 {updated_count}，跳過 {skipped_count}（未變）",
                    level=messages.SUCCESS,
                )
                
            except Exception as e:
                self.message_user(request, f"❌ 爬取 {entity.name} 失敗: {e}", level=messages.ERROR)




class BGGDataStatusFilter(admin.SimpleListFilter):
    """Filter games by BGG data status (0=none, 1=partial, 2=complete)"""
    title = "BGG Data Status"
    parameter_name = "bgg_data_status"

    def lookups(self, request, model_admin):
        return [
            ("0", "No BGG Data (0)"),
            ("1", "Partial BGG Data (1)"),
            ("2", "Complete BGG Data (2)"),
        ]

    def queryset(self, request, queryset):
        from django.db.models import Q
        
        if self.value() == "0":
            # Both category and mechanism are null or empty
            return queryset.filter(
                Q(bgg_category__isnull=True) | Q(bgg_category=[]),
                Q(bgg_mechanism__isnull=True) | Q(bgg_mechanism=[])
            )
        elif self.value() == "1":
            # Only one of them has data
            return queryset.filter(
                Q(
                    Q(bgg_category__isnull=False, bgg_category__ne=[]) &
                    (Q(bgg_mechanism__isnull=True) | Q(bgg_mechanism=[]))
                ) |
                Q(
                    Q(bgg_mechanism__isnull=False, bgg_mechanism__ne=[]) &
                    (Q(bgg_category__isnull=True) | Q(bgg_category=[]))
                )
            )
        elif self.value() == "2":
            # Both have data
            return queryset.filter(
                ~(Q(bgg_category__isnull=True) | Q(bgg_category=[])),
                ~(Q(bgg_mechanism__isnull=True) | Q(bgg_mechanism=[]))
            )
        return queryset


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "canonical_name", "kind", "parent_game", "bgg_id", "affiliate",
        "players_display", "playtime_display",
        "platvm_display",
        "bgg_data_status",
        "sensory_short", "dexterity_short", "spatial_short",
        "reading_density_short",
        "created_at", "updated_at"
    )
    search_fields = ("canonical_name", "bgg_id", "titles__title")
    autocomplete_fields = ("affiliate", "parent_game")
    ordering = ("canonical_name",)
    inlines = (GameTitleInline, DimensionInline, EditionInline)
    list_filter = (
        "kind",
        BGGDataStatusFilter,
        # "min_players", "max_players",
    )
    fieldsets = (
        ("基本資訊", {
            "fields": ("canonical_name", "bgg_id", "affiliate")
        }),
        ("產品屬性", {
            "fields": (
                "kind", "parent_game",
                ("min_players", "max_players"),
                ("min_playtime", "max_playtime"),
            )
        }),
        ("Competencies and Skill", {
            "fields": (
                ("adaptability", "collaboration", "communication",
                "creativity", "critical_thinking", "problem_solving"),
                ("sensory", "dexterity", "spatial"),
                "reading_density",
            )
        }),
        ("BGG Data", {
            "fields": ("bgg_category", "bgg_mechanism"),
            "classes": ("collapse",)
        }),
    )

    _competency_skill_fields = {
        'adaptability', 'collaboration', 'communication',
        'creativity', 'critical_thinking', 'problem_solving',
        'sensory', 'dexterity', 'spatial', 'reading_density',
    }

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        for field_name in self._competency_skill_fields:
            if field_name in form.base_fields:
                form.base_fields[field_name].help_text = ''
        return form


    @admin.display(description="Players", ordering="min_players")
    def players_display(self, obj):
        if obj.min_players is None and obj.max_players is None:
            return "-"
        if obj.min_players == obj.max_players:
            return str(obj.min_players)
        return f"{obj.min_players or '?'}–{obj.max_players or '?'}"

    @admin.display(description="Playtime", ordering="min_playtime")
    def playtime_display(self, obj):
        if obj.min_playtime is None and obj.max_playtime is None:
            return "-"
        if obj.min_playtime == obj.max_playtime:
            return f"{obj.min_playtime}m"
        return f"{obj.min_playtime or '?'}–{obj.max_playtime or '?'}m"

    @admin.display(description="PLATVM")
    def platvm_display(self, obj):
        """Display 6 educational skills as array [adaptability, collaboration, communication, creativity, critical_thinking, problem_solving]"""
        values = [
            obj.adaptability if obj.adaptability is not None else 0,
            obj.collaboration if obj.collaboration is not None else 0,
            obj.communication if obj.communication is not None else 0,
            obj.creativity if obj.creativity is not None else 0,
            obj.critical_thinking if obj.critical_thinking is not None else 0,
            obj.problem_solving if obj.problem_solving is not None else 0,
        ]
        return str(values)

    @admin.display(description="BGG")
    def bgg_data_status(self, obj):
        """
        Display BGG data status:
        0 = both bgg_category and bgg_mechanism are null/empty
        1 = only one of them has data
        2 = both have data
        """
        has_category = obj.bgg_category and len(obj.bgg_category) > 0
        has_mechanism = obj.bgg_mechanism and len(obj.bgg_mechanism) > 0
        
        if has_category and has_mechanism:
            return "2"
        elif has_category or has_mechanism:
            return "1"
        else:
            return "0"

    @admin.display(description="✊🏻Adp")
    def adaptability_short(self, obj):
        return obj.adaptability if obj.adaptability is not None else "-"

    @admin.display(description="🤝Clb")
    def collaboration_short(self, obj):
        return obj.collaboration if obj.collaboration is not None else "-"

    @admin.display(description="👂Com")
    def communication_short(self, obj):
        return obj.communication if obj.communication is not None else "-"

    @admin.display(description="🦄Crv")
    def creativity_short(self, obj):
        return obj.creativity if obj.creativity is not None else "-"

    @admin.display(description="☯️Cth")
    def critical_thinking_short(self, obj):
        return obj.critical_thinking if obj.critical_thinking is not None else "-"

    @admin.display(description="🧩Prs")
    def problem_solving_short(self, obj):
        return obj.problem_solving if obj.problem_solving is not None else "-"

    @admin.display(description="👃Sens")
    def sensory_short(self, obj):
        return "✓" if obj.sensory else "-"

    @admin.display(description="👟Dex")
    def dexterity_short(self, obj):
        return "✓" if obj.dexterity else "-"

    @admin.display(description="🧊Spa")
    def spatial_short(self, obj):
        return "✓" if obj.spatial else "-"

    @admin.display(description="📖Reading Density")
    def reading_density_short(self, obj):
        if not obj.reading_density:
            return "-"
        # Return the display name from choices
        choices_dict = dict(Game._meta.get_field('reading_density').choices)
        return choices_dict.get(obj.reading_density, obj.reading_density)

    @admin.action(description="📊 Calculate Dimensions from BGG Data or Dimension")
    def calculate_dimensions_from_bgg_action(self, request, queryset):
        import json
        import os
        from django.conf import settings
        from .models import Dimension

        processed_count = 0
        error_count = 0
        from_dimension_count = 0
        from_bgg_count = 0

        for game in queryset:
            try:
                # Initialize arrays for OR operation (all zeros)
                arrays = {
                    'adaptability': [0, 0, 0, 0, 0],
                    'collaboration': [0, 0, 0, 0, 0],
                    'communication': [0, 0, 0, 0, 0],
                    'creativity': [0, 0, 0, 0, 0],
                    'critical_thinking': [0, 0, 0, 0, 0],
                    'problem_solving': [0, 0, 0, 0, 0],
                    'basic': [0, 0, 0],  # For sensory, dexterity, spatial
                }

                # Step 1: Check if Dimension exists for this game
                try:
                    dimension = Dimension.objects.get(game=game)
                    # Use existing Dimension data
                    if dimension.adaptability:
                        arrays['adaptability'] = dimension.adaptability
                    if dimension.collaboration:
                        arrays['collaboration'] = dimension.collaboration
                    if dimension.communication:
                        arrays['communication'] = dimension.communication
                    if dimension.creativity:
                        arrays['creativity'] = dimension.creativity
                    if dimension.critical_thinking:
                        arrays['critical_thinking'] = dimension.critical_thinking
                    if dimension.problem_solving:
                        arrays['problem_solving'] = dimension.problem_solving
                    if dimension.basic:
                        arrays['basic'] = dimension.basic
                    
                    from_dimension_count += 1
                    
                except Dimension.DoesNotExist:
                    # Step 2: If Dimension doesn't exist, use BGG data
                    # Load BGG platform data
                    config_path = os.path.join(settings.BASE_DIR, 'game', 'config', 'bgg_platvm.json')
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            bgg_data = json.load(f)
                        # Merge both mechanics and categories
                        mechanics_data = bgg_data.get('mechanics', {})
                        categories_data = bgg_data.get('categories', {})
                        category_data = {**mechanics_data, **categories_data}
                    except Exception as e:
                        messages.error(request, f"❌ Failed to load BGG config for {game.canonical_name}: {e}")
                        error_count += 1
                        continue

                    # Get BGG mechanisms and categories
                    mechanisms = game.bgg_mechanism or []
                    categories = game.bgg_category or []

                    if not mechanisms and not categories:
                        messages.warning(request, f"⚠️ {game.canonical_name} has no BGG data")
                        continue

                    # Process all items from mechanisms and categories
                    all_items = list(mechanisms) + list(categories)

                    for item in all_items:
                        item_data = category_data.get(item)
                        if item_data:
                            # OR operation for each array position
                            for key in ['adaptability', 'collaboration', 'communication', 'creativity', 'critical_thinking', 'problem_solving']:
                                item_array = item_data.get(key, [0, 0, 0, 0, 0])
                                for i in range(5):
                                    if item_array[i] == 1:
                                        arrays[key][i] = 1
                            # Basic array (3 elements)
                            item_basic = item_data.get('basic', [0, 0, 0])
                            for i in range(3):
                                if item_basic[i] == 1:
                                    arrays['basic'][i] = 1

                    # Create Dimension with calculated arrays
                    dimension = Dimension.objects.create(
                        game=game,
                        adaptability=arrays['adaptability'],
                        collaboration=arrays['collaboration'],
                        communication=arrays['communication'],
                        creativity=arrays['creativity'],
                        critical_thinking=arrays['critical_thinking'],
                        problem_solving=arrays['problem_solving'],
                        basic=arrays['basic'],
                    )
                    from_bgg_count += 1

                # Calculate sums for each dimension from arrays
                dimension_scores = {
                    'adaptability': sum(arrays['adaptability']),
                    'collaboration': sum(arrays['collaboration']),
                    'communication': sum(arrays['communication']),
                    'creativity': sum(arrays['creativity']),
                    'critical_thinking': sum(arrays['critical_thinking']),
                    'problem_solving': sum(arrays['problem_solving']),
                }

                # Basic values for sensory, dexterity, spatial
                sensory = arrays['basic'][0]
                dexterity = arrays['basic'][1]
                spatial = arrays['basic'][2]

                # Update Game model with calculated scores (9 fields)
                game.adaptability = dimension_scores['adaptability']
                game.collaboration = dimension_scores['collaboration']
                game.communication = dimension_scores['communication']
                game.creativity = dimension_scores['creativity']
                game.critical_thinking = dimension_scores['critical_thinking']
                game.problem_solving = dimension_scores['problem_solving']
                game.sensory = bool(sensory)
                game.dexterity = bool(dexterity)
                game.spatial = bool(spatial)
                game.save()

                processed_count += 1

            except Exception as e:
                error_count += 1
                messages.error(request, f"❌ Error processing {game.canonical_name}: {e}")

        if processed_count > 0:
            messages.success(request, f"✅ Successfully processed {processed_count} games ({from_dimension_count} from Dimension, {from_bgg_count} from BGG data)")
        if error_count > 0:
            messages.error(request, f"❌ Encountered {error_count} error(s)")
        if error_count == 0 and processed_count == 0:
            messages.warning(request, "⚠️ No games had valid data to process")

    @admin.action(description="Sync selected Games to VPS (upsert only, no deletes)")
    def sync_games_vps_action(self, request, queryset):
        from game.sync_service import GameSyncService

        service = GameSyncService()
        sync_log = service.sync_games(queryset)

        if sync_log.status == 'success':
            messages.success(request, f"📌 成功同步 {queryset.count()} 個遊戲 (共 {sync_log.records_sent} 筆資料, {sync_log.media_sent} 個檔案) 到 VPS。")
        elif sync_log.status == 'partial':
            messages.warning(request, f"⚠️ 部分同步成功: {sync_log.error}")
        else:
            messages.error(request, f"❌ 同步失敗: {sync_log.error}")

    @admin.action(description="⚡ Delta sync to VPS (all changed records — selection ignored)")
    def sync_delta_vps_action(self, request, queryset):
        from game.sync_service import GameSyncService

        service = GameSyncService()
        sync_log = service.run(sync_type="delta")
        self._show_sync_result(request, sync_log, "Delta")

    @admin.action(description="🌐 補送流程圖譯文到 VPS (backfill, selection ignored)")
    def sync_flowchart_texts_action(self, request, queryset):
        from game.sync_service import GameSyncService

        service = GameSyncService()
        sync_log = service.sync_flowchart_texts()

        if sync_log.status == 'success':
            charts = (sync_log.details or {}).get('published_charts', 0)
            messages.success(
                request,
                f"✅ 已補送 {sync_log.records_sent} 筆流程圖譯文（涵蓋 {charts} 張已發布的圖）到 VPS。"
            )
        elif sync_log.status == 'partial':
            messages.warning(request, f"⚠️ 譯文補送部分成功: {sync_log.error}")
        else:
            messages.error(request, f"❌ 譯文補送失敗: {sync_log.error}")

    @admin.action(description="Full sync to VPS (mirror local, deletes orphans — selection ignored)")
    def sync_full_vps_action(self, request, queryset):
        from game.sync_service import GameSyncService

        service = GameSyncService()
        sync_log = service.run(sync_type="full")
        self._show_sync_result(request, sync_log, "Full")

    def _show_sync_result(self, request, sync_log, label):
        if sync_log.status == 'success':
            if sync_log.records_sent == 0 and sync_log.media_sent == 0:
                messages.info(request, f"ℹ️ {label} sync: 沒有需要同步的資料 (一切已同步)")
            else:
                messages.success(
                    request,
                    f"✅ {label} sync 成功: {sync_log.records_sent} 筆資料, "
                    f"{sync_log.media_sent} 個檔案"
                )
        elif sync_log.status == 'partial':
            messages.warning(
                request,
                f"⚠️ {label} sync 部分成功 ({sync_log.records_sent} 筆已送): {sync_log.error}"
            )
        else:
            messages.error(request, f"❌ {label} sync 失敗: {sync_log.error}")

    actions = [
        'calculate_dimensions_from_bgg_action',
        'sync_games_vps_action',
        'sync_delta_vps_action',
        'sync_full_vps_action',
        'sync_flowchart_texts_action',
    ]


@admin.register(GameTitle)
class GameTitleAdmin(admin.ModelAdmin):
    list_display = ("title", "language", "game", "is_primary")
    list_filter = ("language", "is_primary")
    search_fields = ("title", "game__canonical_name")
    autocomplete_fields = ("game", "language")


@admin.register(Dimension)
class DimensionAdmin(admin.ModelAdmin):
    list_display = (
        "game", 
        "adaptability_sum", "collaboration_sum", "communication_sum",
        "creativity_sum", "critical_thinking_sum", "problem_solving_sum",
        "sensory_display", "dexterity_display", "spatial_display",
        # "source_short",
        "source_member",
        "created_at", "updated_at"
    )
    search_fields = ("game__canonical_name",)
    autocomplete_fields = ("game",)
    fields = (
        "game",
        "adaptability", "collaboration", "communication",
        "creativity", "critical_thinking", "problem_solving", "basic",
        "source_member",
    )
    formfield_overrides = {
        models.JSONField: {'widget': forms.Textarea(attrs={'rows': 1, 'cols': 80})},
        models.TextField: {'widget': forms.Textarea(attrs={'rows': 1, 'cols': 80})},
    }
    
    @admin.display(description="✊🏻Adp")
    def adaptability_sum(self, obj):
        if obj.adaptability and isinstance(obj.adaptability, list):
            return sum(obj.adaptability)
        return 0
    
    @admin.display(description="🤝Clb")
    def collaboration_sum(self, obj):
        if obj.collaboration and isinstance(obj.collaboration, list):
            return sum(obj.collaboration)
        return 0
    
    @admin.display(description="👂Com")
    def communication_sum(self, obj):
        if obj.communication and isinstance(obj.communication, list):
            return sum(obj.communication)
        return 0
    
    @admin.display(description="🦄Crv")
    def creativity_sum(self, obj):
        if obj.creativity and isinstance(obj.creativity, list):
            return sum(obj.creativity)
        return 0
    
    @admin.display(description="☯️Cth")
    def critical_thinking_sum(self, obj):
        if obj.critical_thinking and isinstance(obj.critical_thinking, list):
            return sum(obj.critical_thinking)
        return 0
    
    @admin.display(description="🧩Prs")
    def problem_solving_sum(self, obj):
        if obj.problem_solving and isinstance(obj.problem_solving, list):
            return sum(obj.problem_solving)
        return 0
    
    @admin.display(description="👃Sens")
    def sensory_display(self, obj):
        if obj.basic and isinstance(obj.basic, list) and len(obj.basic) > 0:
            return obj.basic[0]
        return 0
    
    @admin.display(description="👟Dex")
    def dexterity_display(self, obj):
        if obj.basic and isinstance(obj.basic, list) and len(obj.basic) > 1:
            return obj.basic[1]
        return 0
    
    @admin.display(description="🧊Spa")
    def spatial_display(self, obj):
        if obj.basic and isinstance(obj.basic, list) and len(obj.basic) > 2:
            return obj.basic[2]
        return 0
    
    # @admin.display(description="Source")
    # def source_short(self, obj):
    #     if obj.source:
    #         return obj.source[:15] + "..." if len(obj.source) > 10 else obj.source
    #     return "-"


class CompanyEntityFilter(admin.SimpleListFilter):
    title = 'Company'
    parameter_name = 'company_entity'

    def lookups(self, request, model_admin):
        from game.models import Entity
        companies = Entity.objects.filter(entity_type='company')
        return [(str(company.id), company.name) for company in companies]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(roles__entity_id=self.value())
        return queryset


class EditionYearAutocompleteJsonView(AutocompleteJsonView):
    """Edition autocomplete 的 JSON view，下拉選項文字後面附上 release year。

    透過 EditionAdmin 註冊的專屬 URL 提供，只給 Rulebook 的 edition 欄位使用，
    不影響其他 edition autocomplete。
    """

    def serialize_result(self, obj, to_field_name):
        result = super().serialize_result(obj, to_field_name)
        year = getattr(obj, "release_year", None)
        if year:
            result["text"] = f"{result['text']} ({year})"
        return result


class EditionYearAutocompleteSelect(AutocompleteSelect):
    """指向 EditionAdmin 專屬 autocomplete URL 的 widget（選項會顯示 release year）。"""

    def get_url(self):
        return reverse("%s:game_edition_autocomplete_year" % self.admin_site.name)


@admin.register(Edition)
class EditionAdmin(admin.ModelAdmin):
    change_list_template = "admin/game/edition/change_list.html"

    def import_view(self, request):
        """版本輸入：貼上格式化文字 → 預覽 → 送審（解析見 game/edition_import.py）。

        送審不寫入 DB，只把文字存進選定的 EditionImportQueue 並改成待approval；
        要到佇列按「寫入DB」才會真正 run_import(commit=True)。
        """
        import hashlib
        from django.core.exceptions import PermissionDenied
        from .edition_import import run_import

        if not request.user.has_perm("game.import_edition"):
            raise PermissionDenied

        Q = EditionImportQueue.Status
        queue_items = list(
            EditionImportQueue.objects.filter(status__in=[Q.SEARCHING, Q.REVIEW]).order_by("name")
        )
        queue_id = request.POST.get("queue_id") or request.GET.get("queue", "")
        queue_item = next((q for q in queue_items if str(q.pk) == queue_id), None)
        text = request.POST.get("text", "")
        if request.method == "GET" and queue_item and queue_item.import_text:
            text = queue_item.import_text   # 待審重送：帶出上次的文字
        report = None
        committed = False
        can_commit = False
        preview_hash = ""
        digest = hashlib.sha256(text.replace(chr(13), "").strip().encode("utf-8")).hexdigest()

        if request.method == "POST" and text.strip():
            report = run_import(text, commit=False)
            if request.POST.get("action") == "commit" and not report.has_errors:
                if queue_item is None:
                    messages.error(request, "請先選擇要送審的桌遊名。")
                elif request.POST.get("preview_hash") != digest:
                    messages.error(request, "文字在預覽後被修改過，請重新預覽。")
                else:
                    queue_item.import_text = text
                    queue_item.status = Q.REVIEW
                    queue_item.save(update_fields=["import_text", "status", "updated_at"])
                    committed = True
                    url = reverse("admin:game_editionimportqueue_change", args=[queue_item.pk])
                    messages.success(request, format_html(
                        "已送審「<a href=\"{}\">{}</a>」，尚未寫入 DB；到Edition import queue按「寫入DB」才會寫入。",
                        url, queue_item.name,
                    ))
            if not committed and not report.has_errors:
                can_commit = True
                preview_hash = digest

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "版本輸入",
            "text": text,
            "report": report,
            "committed": committed,
            "can_commit": can_commit,
            "preview_hash": preview_hash,
            "queue_items": queue_items,
            "queue_id": str(queue_item.pk) if queue_item else "",
        }
        return TemplateResponse(request, "admin/game/edition/import.html", context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="game_edition_import",
            ),
            path(
                "autocomplete-year/",
                self.admin_site.admin_view(
                    EditionYearAutocompleteJsonView.as_view(admin_site=self.admin_site)
                ),
                name="game_edition_autocomplete_year",
            ),
        ]
        return custom_urls + urls

    list_display = (
        "name", "language",
        "release_year", "rank_score_display", "barcode", "thumbnail_image",
        "thumbnail_file_size_display", "thumbnail_optimized",
        "is_primary", "color_vision_short", "updated_at",
    )
    # 不設 ordering = ("-rank_score",)：rank_score 是 annotation，而 Django 有些路徑
    # （self-FK based_on 的 get_field_queryset、ModelAdmin.get_queryset）會拿 get_ordering()
    # 去 order_by 一個沒 annotate 的 queryset，會 FieldError。點欄位標題排序不受影響。
    list_editable = ("thumbnail_optimized",)
    list_filter = ("thumbnail_optimized", CompanyEntityFilter, "region", "is_primary", "language", "color_vision_friendly", )
    search_fields = (
        "game__canonical_name",
        "name",
        "slug",
        "barcode",
        "roles__entity__name",
    )

    autocomplete_fields = ("game", "language", "region", "based_on")
    filter_horizontal = ("packaging_languages",)
    readonly_fields = ("view_count",)

    fieldsets = (
        ("Identity", {
            "fields": (
                "game", "name", "slug", "release_year", "region", "barcode", "msrp", "msrp_currency", "is_primary", "based_on",
            ),
            "description": (
                "slug 是這個版本的公開網址（/games/&lt;slug&gt;/）。改名<b>不會</b>自動更新 slug —— "
                "線上網址必須穩定。真要換網址請用下方的「重新產生 SEO 網址」動作，它會把舊網址留成 301。"
            ),
        }),
        ("Languages", {
            "fields": (
                "language", "packaging_languages",
            )
        }),
        ("Box / Display", {
            "fields": (
                "thumbnail", "thumbnail_optimized", "summary", "age", "color_vision_friendly",
            )
        }),
        ("Statistics", {
            "fields": (
                "view_count",
            )
        }),
        # ("Players / Time", {
        #     "fields": (
        #         ("min_players", "max_players"),
        #         ("min_playtime", "max_playtime"),
        #     )
        # }),
    )

    inlines = (EditionRoleInline, RulebookInline, ComponentInline,)

    def get_queryset(self, request):
        # 分值定義與 /games/ 瀏覽頁共用（game/selectors.py），兩邊一定一致。
        # select_related 順便修掉 list 頁 language / game 的 N+1。
        from game.selectors import annotate_rank_score

        return annotate_rank_score(
            super().get_queryset(request).select_related("game", "language")
        )

    # 三個數字拆開顯示是刻意的：調公式時要看得出是哪一項在動
    @admin.display(description="排序值", ordering="rank_score")
    def rank_score_display(self, obj):
        return f"{obj.rank_score:.2f}（完整 {obj.completeness_score:.0f} + 新發布 {obj.recency_score:.2f}）"

    @admin.display(description="Thumbnail")
    def thumbnail_image(self, obj):
        if obj.thumbnail:
            return format_html('<img src="{}" style="width: 50px; height: 50px; object-fit: contain;" />', obj.thumbnail.url)
        return "-"

    @admin.display(description="Size")
    def thumbnail_file_size_display(self, obj):
        if obj.thumbnail and hasattr(obj.thumbnail, 'size'):
            size = obj.thumbnail.size
            return f"{int(size / 1024)} KB"
        return "-"

    # 三態要一眼分得出來：✓ 友善／✗ 需辨色／- 尚未確認（前台只有 ✓ 那組會出 icon）
    @admin.display(description="🎨CVF", ordering="color_vision_friendly")
    def color_vision_short(self, obj):
        if obj.color_vision_friendly is None:
            return "-"
        return "✓" if obj.color_vision_friendly else "✗"

    actions = ["resize_to_webp", "regenerate_slug"]

    @admin.action(description="🔗 重新產生 SEO 網址（舊網址保留 301）")
    def regenerate_slug(self, request, queryset):
        """
        依目前的 name / release_year 重算 slug，並把舊 slug 記進 EditionSlugAlias
        以便發 301。這是唯一會改動線上網址的路徑。
        """
        from game.models import EditionSlugAlias
        from game.slugs import build_unique_edition_slug

        changed = unchanged = 0
        for edition in queryset.select_related("game"):
            old = edition.slug
            new = build_unique_edition_slug(edition)
            if old == new:
                unchanged += 1
                continue
            edition.slug = new
            edition.save(update_fields=["slug"])
            if old:
                EditionSlugAlias.objects.get_or_create(slug=old, defaults={"edition": edition})
            changed += 1

        if changed:
            self.message_user(request, f"已更新 {changed} 筆網址，舊網址已保留為 301。")
        if unchanged:
            self.message_user(request, f"{unchanged} 筆網址無變化。")

    @admin.action(description="📐 Resize to max 400px and convert to WebP")
    def resize_to_webp(self, request, queryset):
        """Resize thumbnails to max 400px (width/height) and convert to WebP format"""
        from PIL import Image
        import io
        from django.core.files.base import ContentFile
        import os

        success_count = 0
        skip_count = 0
        error_count = 0

        for edition in queryset:
            if not edition.thumbnail:
                skip_count += 1
                continue

            try:
                # Open the original image
                with Image.open(edition.thumbnail.path) as img:
                    # Convert to RGBA to support transparency if needed
                    # if img.mode != 'RGBA':
                    #     img = img.convert('RGBA')
                    
                    # 【新增這行】把原圖的色彩描述檔擷取下來
                    icc = img.info.get('icc_profile')
    
                    # 處理 CMYK (如果是印刷檔，必須正確轉換為 RGB)
                    if img.mode == 'CMYK':
                        img = img.convert('RGB')
                    elif img.mode in ("RGBA", "P"):
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        if img.mode == "RGBA":
                            background.paste(img, mask=img.split()[3])
                        else:
                            background.paste(img)
                        img = background
                    elif img.mode != "RGB":
                        img = img.convert("RGB")

                    # Calculate new dimensions maintaining aspect ratio
                    width, height = img.size
                    if width > 400 or height > 400:
                        if width > height:
                            new_width = 400
                            new_height = int(height * (400 / width))
                        else:
                            new_height = 400
                            new_width = int(width * (400 / height))
                        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                    # Save to WebP format
                    img_bytes = io.BytesIO()
                    # img.save(img_bytes, format='WEBP', quality=85)
                    img.save(img_bytes, format='WEBP', quality=85, method=6, icc_profile=icc)
                    img_bytes.seek(0)

                    # Change file extension to .webp
                    original_name = edition.thumbnail.name
                    if original_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                        new_name = os.path.splitext(original_name)[0] + '.webp'
                    else:
                        new_name = original_name + '.webp'

                    # Save the processed image
                    edition.thumbnail.save(
                        new_name,
                        ContentFile(img_bytes.read()),
                        save=True
                    )

                    # Mark as optimized
                    edition.thumbnail_optimized = True
                    edition.save(update_fields=['thumbnail_optimized'])

                    success_count += 1

            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f"❌ Failed to process {edition}: {str(e)}",
                    level=messages.WARNING
                )

        self.message_user(
            request,
            f"✅ Resize completed: {success_count} success, {skip_count} skipped (no thumbnail), {error_count} errors",
            level=messages.SUCCESS
        )


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
    list_display = (
        "name", "component_type", "material", "quantity",
        "edition", "updated_at",
    )
    list_filter = ("component_type", "material")
    search_fields = (
        "name",
        "edition__name",
        "edition__game__canonical_name",
    )
    autocomplete_fields = ("edition",)
    fieldsets = (
        (None, {
            "fields": ("edition", "name", "component_type", "material", "quantity"),
        }),
        ("詳細資料", {
            "fields": ("description",),
            "classes": ("collapse",),
        }),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Inject choices for component_type and material without adding them to the model."""
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "component_type":
            field.widget = forms.Select(
                choices=[("" , "---------")] + list(COMPONENT_TYPE_CHOICES)
            )
        elif db_field.name == "material":
            field.widget = forms.Select(
                choices=[("" , "---------")] + list(COMPONENT_MATERIAL_CHOICES)
            )
        return field


@admin.register(RulebookNode)
class RulebookNodeAdmin(admin.ModelAdmin):
    list_display = [
        "id_short", "rulebook", "tag_path", "ruleset", "title", "depth", "is_leaf", 
        "page", "token_count", "sync_status_colored", "vector_synced_at"
    ]
    list_filter = ["is_leaf", "ruleset", "vector_sync_status", "language", "game", "depth"]
    search_fields = ["tag_path", ]#"title", "text", "rulebook__title", "game__canonical_name"]
    readonly_fields = [
        "id", "game", "edition", "text_hash", "vector_point_id",
        "vector_synced_at", "created_at", "updated_at"
    ]
    
    fieldsets = (
        ("Hierarchy", {
            "fields": ("id", "parent", "rulebook", ("game", "edition"), "language")
        }),
        ("Node Info", {
            "fields": ("tag_path", "ruleset", "title", "depth", "sibling_order", "is_leaf")
        }),
        ("Content", {
            "fields": ("page", "text", "text_hash", "token_count", "metadata")
        }),
        ("Vector Sync Status", {
            "fields": (
                "vector_sync_status", "vector_point_id", "vector_collection",
                "embedding_model", "embedding_version", "vector_synced_at", "vector_last_error"
            ),
            "classes": ("collapse",)
        }),
        ("Other", {
            "fields": ("child_index", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    list_per_page = 50
    @admin.display(description="ID")
    def id_short(self, obj):
        return str(obj.id)[:8]

    @admin.action(description="Mark status as Pending")
    def mark_pending(self, request, queryset):
        leaf_nodes = queryset.filter(is_leaf=True)
        updated = leaf_nodes.update(vector_sync_status="pending")
        self.message_user(request, f"已將 {updated} 個葉節點標記為待同步")

    @admin.action(description="標記為已同步 (Synced)")
    def mark_synced(self, request, queryset):
        from django.utils import timezone
        leaf_nodes = queryset.filter(is_leaf=True)
        updated = leaf_nodes.update(
            vector_sync_status="synced",
            vector_synced_at=timezone.now()
        )
        self.message_user(request, f"已將 {updated} 個葉節點標記為已同步")

    @admin.display(description="同步狀態")
    def sync_status_colored(self, obj):
        if not obj.is_leaf:
            return mark_safe('<span style="color: #6C757D;">-</span>')
        colors = {
            "pending": "#FFA500",
            "synced": "#28A745",
            "failed": "#DC3545",
        }
        color = colors.get(obj.vector_sync_status, "#6C757D")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_vector_sync_status_display()
        )





    

    

    
# @admin.register(HeadingRule)
# class HeadingRuleAdmin(admin.ModelAdmin):
#     list_display = ("category", "priority", "language_code", "enabled", "pattern")
#     list_filter = ("enabled", "category", "language_code")
#     search_fields = ("category", "pattern", "note")
#     ordering = ("priority", "category")
#     list_editable = ("priority", "enabled")  # 讓你在列表直接改 priority/enabled


@admin.action(description="(RAG) 1A. Extract by LlamaParse (with markdown)")
def extract_and_clean_rulebooks_llamaparse(modeladmin, request, queryset):
    if _block_heavy_in_production(request):
        return
    queued = skipped = 0

    for rb in queryset:
        if not rb.file:
            skipped += 1
            continue

        try:
            async_task("game.tasks.process_rulebook_llamaparse_task", str(rb.id))
            queued += 1
        except Exception as e:
            modeladmin.message_user(request, f"❌ Error queuing {rb}: {str(e)}", messages.ERROR)

    modeladmin.message_user(
        request,
        f"Queued {queued} rulebook(s) for LlamaParse extraction. Skipped {skipped}. Check status in the list view.",
        messages.INFO
    )

# LlamaParse 不一定會照 prompt 套用座標規範，人工修 whole_context 時常要自己補。
# 放在 Rulebook 編輯頁「文字內容」區塊上方，讓人直接整段複製貼進 whole_context。
GRID_COORDINATE_SNIPPET = """[context note: visual data conventions]
Coordinates:
- A1 = bottom-left tile.
- Letters increase left to right.
- Numbers increase bottom to top.
- On hex grids, odd-lettered columns are shifted upward by half a hex.
- Edge = shared side of two adjacent tiles.
- Vertex = point where multiple tiles meet.
[/context note]"""

# 上面那段只定義座標規範；這段示範規範要怎麼套到內文，放在對應圖片/圖表的位置。
IMAGE_DATA_SAMPLE_SNIPPET = """[image data: Recommended setup]
Grid type: Hexagonal
Grid size: 6 rows × 6 columns
Occupied positions: 24
A1: mountain, disc 6
A2: fields, disc 3
Edge A1-B1: road
Vertex A1-A2-B1: settlement
[/image data]"""


def _snippet_block(label, snippet):
    """編輯頁上的一段「可整段複製」範例：標題 + 等寬區塊。"""
    return format_html(
        "<p style=\"margin:0 0 6px;font-weight:600;color:var(--body-fg);\">{}</p>"
        "<pre style=\"margin:0 0 12px;padding:10px;border-radius:4px;"
        "background:var(--darkened-bg);color:var(--body-fg);"
        "border:1px solid var(--hairline-color);"
        "white-space:pre;overflow-x:auto;user-select:all;"
        "font-family:Menlo,Consolas,monospace;font-size:12px;line-height:1.5;\">{}</pre>",
        label,
        snippet,
    )


GRID_COORDINATE_HINT = format_html(
    "{}{}",
    _snippet_block("📐 Grid coordinates（人工編輯 whole_context 時可整段複製）", GRID_COORDINATE_SNIPPET),
    _snippet_block("🧩 內文中的用法範例（放在對應圖片／圖表的位置）", IMAGE_DATA_SAMPLE_SNIPPET),
)

@admin.action(description="💫1️⃣Extract by LlamaParse (whole context)")
def extract_rulebooks_whole_context(modeladmin, request, queryset):
    """全文擷取（無 markdown 分層），只寫 extracted_text，不動 whole_context 與舊欄位。"""
    if _block_heavy_in_production(request):
        return
    queued = skipped = 0

    for rb in queryset:
        if not rb.file:
            skipped += 1
            continue

        try:
            async_task("game.tasks.process_rulebook_whole_context_task", str(rb.id))
            queued += 1
        except Exception as e:
            modeladmin.message_user(request, f"❌ Error queuing {rb}: {str(e)}", messages.ERROR)

    modeladmin.message_user(
        request,
        f"Queued {queued} rulebook(s) for whole-context extraction. Skipped {skipped}. "
        f"結果一律只寫入 extracted_text，⚠️ 不會動到 whole_context（人工調整區）。"
        f"要啟用新原稿，請在編輯頁把 extracted_text 複製貼上到 whole_context。"
        f"不影響 status / nodes。",
        messages.INFO
    )

@admin.action(description="(RAG) 1B. Extract by PyMuPDF (markdown)")
def extract_rulebooks_pymupdf(modeladmin, request, queryset):
    if _block_heavy_in_production(request):
        return
    import time
    from .rag.rulebook_processing import extract_text_from_pdf_with_ocr
    
    processed = skipped = failed = 0
    total_time = 0

    for rb in queryset:
        if not rb.file:
            skipped += 1
            continue

        start_time = time.time()

        try:
            from .tasks import _count_tokens, _detect_languages
            language = rb.language.language if rb.language else "en"
            text, needs_ocr = extract_text_from_pdf_with_ocr(rb.file, language=language)

            rb.extracted_text = text
            rb.needs_ocr = needs_ocr
            rb.ocr_done = True
            rb.status = "parsed"
            rb.pdf_token_count = _count_tokens(text)
            rb.content_languages = _detect_languages(text)

            rb.save(update_fields=[
                "extracted_text", "needs_ocr", "ocr_done",
                "status", "pdf_token_count", "content_languages", "updated_at"
            ])
            
            processing_time = time.time() - start_time
            total_time += processing_time
            processed += 1
            
            # Show individual result
            ocr_status = "🔍 OCR used" if needs_ocr else "📝 Text only"
            modeladmin.message_user(
                request,
                f"✅ {rb.title}: {ocr_status} ({len(text)} chars, {processing_time:.1f}s)",
                level=messages.SUCCESS
            )
            
        except Exception as e:
            failed += 1
            try:
                rb.status = "pending"
                rb.save(update_fields=["status", "updated_at"])
            except:
                pass
            modeladmin.message_user(
                request,
                f"❌ {rb.title} failed: {str(e)}",
                level=messages.ERROR
            )

    # Summary message
    if processed > 0:
        avg_time = total_time / processed
        modeladmin.message_user(
            request,
            f"📊 PyMuPDF Summary: {processed} processed, {skipped} skipped, {failed} failed. "
            f"Avg time: {avg_time:.1f}s per rulebook.",
            level=messages.INFO
        )
    else:
        modeladmin.message_user(
            request,
            f"No rulebooks processed. Skipped: {skipped}, Failed: {failed}",
            level=messages.WARNING
        )
    
@admin.action(description="(RAG) 3. RAG Ingest (Chunk & Index)")
def run_rag_ingest_full(modeladmin, request, queryset):
    if _block_heavy_in_production(request):
        return
    queued = 0
    failed = 0

    for rulebook in queryset:
        try:
            async_task("game.tasks.process_rag_ingest_task", str(rulebook.id))
            queued += 1
        except Exception as e:
            failed += 1
            modeladmin.message_user(
                request,
                f"❌ Error queuing {rulebook.title}: {str(e)}",
                level=messages.ERROR,
            )

    modeladmin.message_user(
        request,
        f"✅ Queued {queued} rulebook(s) for RAG Ingest (Chunk & Index) in background. Failed: {failed}. Check logs for details.",
        level=messages.INFO if queued > 0 else messages.WARNING,
    )


def _queue_flowchart_generation(modeladmin, request, queryset, model=None, label=GEMINI_MAIN_MODEL):
    """
    Bulk-generate flowcharts for selected rulebooks (always detailed level).

    model=None 走 FlowchartService 的 Gemini 預設模型（GEMINI_MAIN_MODEL）。

    注意：RulebookFlowchart 的唯一鍵是 (rulebook, ruleset)，所以同一本規則書
    重跑會「覆蓋」上一張圖，不會並存。
    """
    # regenerate 寫死 True，而 service.get_or_generate() 在 regenerate 時會把
    # adjusted_json 清成 None——人工在編輯器做的排版與所有修改直接消失，沒有備份。
    # 實務上幾乎每張上線的圖都被人工調整過，所以先點名哪些會被蓋掉。
    # 只有 ruleset="basic" 的圖會被覆蓋（身份鍵是 rulebook+ruleset，見 get_or_generate
    # 的 lookup，而這裡固定送 "basic"），其他 ruleset 的圖不受影響。
    clobbered = list(
        RulebookFlowchart.objects
        .filter(rulebook__in=queryset, ruleset="basic", adjusted_json__isnull=False)
        .values_list("rulebook__title", flat=True)
    )
    if clobbered:
        modeladmin.message_user(
            request,
            format_html(
                "⚠️ 已送出，但這 {} 本規則書的 basic 流程圖有人工調整，重新生成完成後"
                "人工排版與修改會被清空且無法復原：{}。"
                "若不想覆蓋，請立刻到 Django Q 的 Queued tasks 刪掉該任務"
                "（worker 可能已經開始跑，不保證來得及）。",
                len(clobbered), "、".join(clobbered),
            ),
            level=messages.WARNING,
        )

    queued = skipped = failed = 0
    for rulebook in queryset:
        if not rulebook.whole_context:
            skipped += 1
            modeladmin.message_user(
                request,
                f"⏭ Skipped '{rulebook.title}': no whole_context "
                f"(run 💫1️⃣Extract by LlamaParse first)",
                level=messages.WARNING,
            )
            continue
        try:
            async_task(
                "game.tasks.generate_flowcharts_task",
                str(rulebook.id),
                "basic",        # ruleset
                True,           # regenerate
                ["detailed"],   # detail levels
                model,          # None = 預設模型
            )
            queued += 1
        except Exception as e:
            failed += 1
            modeladmin.message_user(request, f"❌ Error queuing '{rulebook.title}': {e}", level=messages.ERROR)

    modeladmin.message_user(
        request,
        f"✅ Queued {queued} rulebook(s) for flowchart generation (detailed, {label}). "
        f"Skipped {skipped}, failed {failed}.",
        level=messages.INFO if queued > 0 else messages.WARNING,
    )


@admin.action(description=f"📊 Generate Flowcharts（{GEMINI_MAIN_MODEL}）")
def generate_flowcharts_action(modeladmin, request, queryset):
    _queue_flowchart_generation(modeladmin, request, queryset)


PAGE_MARKER_RE = re.compile(r"<PAGE:\d+>\s*", re.IGNORECASE)
FIGURE_MARKER_RE = re.compile(r"<FIGURE:[0-9a-f\-]+>\s*", re.IGNORECASE)


@admin.action(description="(RAG) 🔧 手動改動節點後同步 (Smart Sync)")
def index_to_qdrant(modeladmin, request, queryset):
    """
    標準同步：只更新有變動的 chunks (Hash 不同或狀態非 Synced)
    """
    _run_indexing(modeladmin, request, queryset)


def _run_indexing(modeladmin, request, queryset):
    """
    內部共用邏輯
    """
    from game.rag.indexing_service import index_rulebook  # lazy：避免啟動時載入重型依賴

    total_stats = {"total": 0, "indexed": 0, "skipped": 0, "failed": 0}

    for rulebook in queryset:
        try:
            stats = index_rulebook(rulebook, force_reindex=False)
            for key in total_stats:
                total_stats[key] += stats[key]
        except Exception as e:
            messages.error(request, f"Failed to index {rulebook}: {e}")
            total_stats["failed"] += rulebook.child_chunks.count() if hasattr(rulebook, 'child_chunks') else 0
    
    msg_type = messages.SUCCESS if total_stats['failed'] == 0 else messages.WARNING
    modeladmin.message_user(
        request,
        f"[SMART SYNC] "
        f"Indexed: {total_stats['indexed']}, "
        f"Skipped: {total_stats['skipped']}, "
        f"Failed: {total_stats['failed']}",
        level=msg_type
    )


@admin.action(description="(RAG) 🔍 Diagnose Qdrant status")
def diagnose_qdrant(modeladmin, request, queryset):
    """檢查 Qdrant 連線、collection 維度、向量數量、及 DB sync 狀態"""
    from game.rag.qdrant_service import get_qdrant_service
    from game.models import RulebookNode
    from django.conf import settings

    qs = get_qdrant_service()

    # 1. Qdrant 連線
    if not qs.health_check():
        modeladmin.message_user(request, "❌ 無法連線 Qdrant！請確認容器是否運行。", level=messages.ERROR)
        return

    # 2. Collection 維度 & 點數
    node_coll = getattr(settings, "QDRANT_NODES_COLLECTION_NAME", "rulebook_nodes")
    qa_coll = getattr(settings, "QDRANT_QA_COLLECTION_NAME", "rulebook_qas")
    expected_dim = getattr(settings, "EMBEDDING_DIMENSION", 3072)

    for coll in [node_coll, qa_coll]:
        info = qs.get_collection_info(coll)
        if not info:
            modeladmin.message_user(request, f"⚠️ Collection '{coll}' 不存在", level=messages.WARNING)
            continue
        try:
            coll_detail = qs.client.get_collection(coll)
            actual_dim = coll_detail.config.params.vectors.size
            dim_ok = actual_dim == expected_dim
            modeladmin.message_user(
                request,
                f"{'✅' if dim_ok else '❌'} Collection '{coll}': "
                f"{info.get('points_count', '?')} points, "
                f"dim={actual_dim} (expected {expected_dim})"
                + ("" if dim_ok else " ← 維度不符！需刪除 collection 後重新 ingest"),
                level=messages.SUCCESS if dim_ok else messages.ERROR,
            )
        except Exception as e:
            modeladmin.message_user(request, f"⚠️ 無法取得 '{coll}' 詳細資訊: {e}", level=messages.WARNING)

    # 3. 每本 rulebook 的 DB sync 狀態
    for rb in queryset:
        nodes_qs = RulebookNode.objects.filter(rulebook=rb)
        total = nodes_qs.count()
        synced = nodes_qs.filter(vector_sync_status="synced").count()
        failed = nodes_qs.filter(vector_sync_status="failed").count()
        pending = nodes_qs.filter(vector_sync_status="pending").count()
        leaf_synced = nodes_qs.filter(is_leaf=True, vector_sync_status="synced").count()
        leaf_total = nodes_qs.filter(is_leaf=True).count()

        # 取一個 failed 的 error 訊息
        sample_error = ""
        failed_node = nodes_qs.filter(vector_sync_status="failed").first()
        if failed_node and failed_node.vector_last_error:
            sample_error = f" | 錯誤樣本: {failed_node.vector_last_error[:120]}"

        level = messages.SUCCESS if synced == total and total > 0 else messages.ERROR
        modeladmin.message_user(
            request,
            f"📋 [{rb.title}] Nodes: total={total}, synced={synced}, failed={failed}, pending={pending} "
            f"(leaf synced: {leaf_synced}/{leaf_total}){sample_error}",
            level=level,
        )


@admin.action(description="(RAG) 🗑️ Delete vectors from Qdrant")
def delete_from_qdrant(modeladmin, request, queryset):
    """從 Qdrant 刪除選中 rulebooks 的向量"""
    from game.rag.indexing_service import get_indexing_service
    
    service = get_indexing_service()
    deleted = 0
    failed = 0
    errors = []
    
    for rulebook in queryset:
        try:
            if service.delete_rulebook_vectors(str(rulebook.id)):
                rulebook.status = "validated"
                rulebook.save(update_fields=["status", "updated_at"])
                deleted += 1
            else:
                failed += 1
                errors.append(f"{rulebook}: delete_rulebook_vectors returned False")
        except Exception as e:
            failed += 1
            errors.append(f"{rulebook}: {e}")
    
    # 顯示結果
    if deleted > 0:
        messages.success(request, f"✅ 成功刪除 {deleted} 本 rulebook 的向量")
    
    if failed > 0:
        messages.warning(request, f"⚠️ 失敗 {failed} 本")
        # 顯示前 3 個錯誤（避免太多訊息）
        for error in errors[:3]:
            messages.error(request, error)
        if len(errors) > 3:
            messages.error(request, f"... 還有 {len(errors) - 3} 個錯誤")
    

class RagTestForm(forms.Form):
    rulebook = forms.ModelChoiceField(
        queryset=Rulebook.objects.all(),
        required=True,
        help_text="先選擇要檢索的 rulebook"
    )
    query = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=True
    )
    top_k = forms.IntegerField(initial=5, min_value=1, max_value=20, required=True)


class ClassifyQuestionTestForm(forms.Form):
    question = forms.CharField(
        label="問題",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=True,
        help_text="輸入一句玩家可能會問的規則問題，用 gemini-3.1-flash-lite 分類（不需要選規則書，分類器不看規則書內容）"
    )



# --- 1. 核心驗證函數 ---
def count_tokens(text, model_name="gpt-4o"):
    """使用 OpenAI 的 tiktoken 計算 token 數量"""
    try:
        encoding = tiktoken.encoding_for_model(model_name)
        return len(encoding.encode(text))
    except Exception:
        # 如果套件載入失敗，使用粗略估算 (約 4 個字元 1 token)
        return len(text) // 4

def validate_markdown_hierarchy(text):
    """
    驗證 markdown 文件的標題層級、tag 命名、attribute 限制與內文格式。

    規則：
    1. Root-level tag 必須是 VALID_CATEGORIES 之一
    2. Tag 每個 segment 必須是 snake_case（僅小寫字母、數字、底線）
    3. 同一 (tag, ruleset) 配對不可在文件中重複出現（會被 chunker 靜默合併，導致 title 丟失）
    4. `#` 數量必須等於 root_level + tag dot 深度（例：根層 `##`，則 [setup.solo] 必須是 `###`）
    5. Sub-tag（含點號）的父層必須先出現於前文
    6. 標題 attribute 只允許 `{ruleset: ...}`，且值必須是 snake_case
    7. Attribute 不可含引號或非法字元（如 `{ruleset: "Don't"}` 會被 chunker 靜默丟棄）
    8. 內文不允許粗體 Markdown (`**`)
    9. Leaf heading 內文不可過短（< MIN_LEAF_TOKENS），避免 embedding 訊號過弱
    """
    from game.rag.constants import VALID_CATEGORIES as ALLOWED_ROOT_TAGS

    # 嚴格版：與 chunker.ATTR_RE 同步，能成功 parse 的合法 attribute
    ATTR_RE = re.compile(r"\{([a-zA-Z0-9_]+):\s*['\"]?([^'\"}]*)['\"]?\s*\}")
    # 寬鬆版：抓所有 {...} 區塊，用以偵測格式錯誤的 attribute
    LOOSE_ATTR_RE = re.compile(r'\{[^{}]*\}')
    BOLD_MD_RE = re.compile(r'\*\*')
    # snake_case：僅小寫字母、數字、底線
    SAFE_NAME_RE = re.compile(r'^[a-z0-9_]+$')

    ALLOWED_ATTR_KEYS = {"ruleset"}
    # leaf chunk 內文 token 下限。30 是 embedding 可靠度的實務下限；
    # 30~80 仍可用，只要內容完整；< 30 通常是不完整段落或純跳轉提示。
    MIN_LEAF_TOKENS = 30

    errors = []
    seen_tags = set()        # 只記 tag，用於父層存在性檢查
    seen_keys = set()        # 記 (tag, ruleset)，用於重複偵測（與 chunker cache_key 同步）
    root_level = None

    # 累積每個 heading 之下的內文 token 數，迴圈結束後做 leaf 檢查
    headings = []            # list of dicts: line_num, tag, clean_line, content_tokens
    current_buffer = []      # 當前 heading 之下累積的內文行
    current_meta = None      # 當前 heading 的 metadata；新 heading 觸發時 flush

    for line_num, line in enumerate(text.strip().split('\n'), 1):
        clean_line = line.strip()
        if not clean_line:
            continue

        # --- 內文（非標題）---
        if not clean_line.startswith('#'):
            if BOLD_MD_RE.search(clean_line):
                errors.append(f"⚠️ 第 {line_num} 行：[BOLD_MARKDOWN] 發現粗體 Markdown (`**`)，建議使用純文字替代！ ➔ {clean_line}")
            if current_meta is not None:
                current_buffer.append(clean_line)
            continue

        # --- 標題 ---
        # 進入新 heading：先封存前一個 heading 的內文 token 數
        if current_meta is not None:
            blob = ' '.join(current_buffer)
            current_meta['content_tokens'] = count_tokens(blob) if blob else 0
            current_meta['content_lines'] = list(current_buffer)
            headings.append(current_meta)
        current_buffer = []
        current_meta = None

        hash_match = re.match(r'^(#+)', clean_line)
        if not hash_match:
            continue
        level = len(hash_match.group(1))

        start_idx = clean_line.find('[')
        end_idx = clean_line.find(']', start_idx)
        if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
            errors.append(f"❌ 第 {line_num} 行：缺少或格式錯誤的 [tag] ➔ {clean_line}")
            continue
        tag = clean_line[start_idx+1:end_idx].strip()

        if root_level is None:
            root_level = level

        # 預先抓取 ruleset 值（完整 attribute 驗證仍在第 6 步進行）
        title_part = clean_line[end_idx+1:]
        node_ruleset = "basic"
        for m in ATTR_RE.finditer(title_part):
            if m.group(1) == "ruleset":
                node_ruleset = m.group(2).strip() or "basic"
                break

        # 0. Tag 後面必須有標題文字
        bare_title = ATTR_RE.sub("", title_part).strip()
        if not bare_title:
            errors.append(f"❌ 第 {line_num} 行：[MISSING_TITLE] 標題 [{tag}] 後面缺少標題文字 ➔ {clean_line}")

        # 1. Root-level tag 限制
        if level == root_level and tag not in ALLOWED_ROOT_TAGS:
            errors.append(f"❌ 第 {line_num} 行：第一層標籤錯誤！必須是 {sorted(ALLOWED_ROOT_TAGS)} 之一，目前為 [{tag}]")

        # 2. Tag 每個 segment 必須是 snake_case
        for seg in tag.split('.'):
            if not SAFE_NAME_RE.match(seg):
                errors.append(f"❌ 第 {line_num} 行：tag 子段『{seg}』必須是 snake_case（僅 a-z, 0-9, 底線，不可大寫或含符號）➔ [{tag}]")
                break  # 同一 tag 只報一次

        # 3. (tag, ruleset) 配對重複（chunker 會靜默合併，title 會丟失）
        node_key = (tag, node_ruleset)
        if node_key in seen_keys:
            errors.append(f"❌ 第 {line_num} 行：[DUPLICATE_TAG] 標籤 [{tag}] (ruleset='{node_ruleset}') 在文件中已出現過！第二段內容會被靜默合併到第一段 node，title 會遺失 ➔ {clean_line}")

        # 4. # 數量必須對齊 tag dot 深度
        dot_count = tag.count('.')
        expected_level = root_level + dot_count
        if level != expected_level:
            errors.append(f"❌ 第 {line_num} 行：[LEVEL_MISMATCH] `#` 數量({level}) 與 tag dot 深度不一致！[{tag}] 有 {dot_count} 個點，應使用 `{'#' * expected_level}` ➔ {clean_line}")

        # 5. Sub-tag 父層必須先出現
        if level > root_level:
            parent_tag = ".".join(tag.split('.')[:-1])
            if parent_tag and parent_tag not in seen_tags:
                errors.append(f"❌ 第 {line_num} 行：[SEMANTIC_ERROR_MARKER] 語義孤兒！標籤 [{tag}] 找不到它的父層級 [{parent_tag}]。")

        # 6. Attribute 檢查（title_part 已在前面取出）

        # 6a. 偵測格式錯誤的 attribute（嚴格 regex 抓不到、會被 chunker 靜默忽略）
        for loose_match in LOOSE_ATTR_RE.finditer(title_part):
            block = loose_match.group(0)
            if not ATTR_RE.fullmatch(block):
                errors.append(f"❌ 第 {line_num} 行：attribute 格式錯誤『{block}』！正確格式為 {{ruleset: 'value'}}，value 不可含引號或 `}}` ➔ {clean_line}")

        # 6b. 對能成功 parse 的 attribute 檢查 key 與 value
        for m in ATTR_RE.finditer(title_part):
            attr_key = m.group(1)
            attr_val = m.group(2).strip()
            if attr_key not in ALLOWED_ATTR_KEYS:
                errors.append(f"❌ 第 {line_num} 行：不允許的 attribute『{{{attr_key}: ...}}』！僅允許 {sorted(ALLOWED_ATTR_KEYS)} ➔ {clean_line}")
                continue
            if not SAFE_NAME_RE.match(attr_val):
                errors.append(f"❌ 第 {line_num} 行：ruleset 值『{attr_val}』必須是 snake_case（僅 a-z, 0-9, 底線，不可大寫或含空白/符號）➔ {clean_line}")

        seen_tags.add(tag)
        seen_keys.add(node_key)

        # 設定 current_meta，讓後續內文行累積到此 heading
        current_meta = {
            'line_num': line_num,
            'tag': tag,
            'ruleset': node_ruleset,
            'clean_line': clean_line,
        }

    # 迴圈結束：封存最後一個 heading
    if current_meta is not None:
        blob = ' '.join(current_buffer)
        current_meta['content_tokens'] = count_tokens(blob) if blob else 0
        current_meta['content_lines'] = list(current_buffer)
        headings.append(current_meta)

    # 預先按 ruleset 分組 tag，is_leaf 判斷只看同 ruleset 內有沒有子 tag
    tags_by_ruleset: dict[str, set[str]] = {}
    for h in headings:
        tags_by_ruleset.setdefault(h['ruleset'], set()).add(h['tag'])

    def _is_leaf(h: dict) -> bool:
        same_rs_tags = tags_by_ruleset.get(h['ruleset'], set())
        return not any(other.startswith(h['tag'] + '.') for other in same_rs_tags)

    # 10. Non-leaf heading 不可有直接內文
    _structural_line_re = re.compile(r"^<(?:PAGE:\d+|FIGURE:[0-9a-f\-]+)>$", re.IGNORECASE)
    for h in headings:
        if not _is_leaf(h):
            body_lines = [l for l in h.get('content_lines', []) if not _structural_line_re.match(l)]
            if body_lines:
                errors.append(
                    f"❌ 第 {h['line_num']} 行：[NON_LEAF_BODY] 非 leaf 標題 [{h['tag']}] 之下有直接內文"
                    f"（擁有子標題的 heading 不可有內文，只能有子標題）➔ 例如：{body_lines[0]!r}"
                )

    # 9. Leaf heading 內文不可過短
    for h in headings:
        if _is_leaf(h) and 0 < h['content_tokens'] < MIN_LEAF_TOKENS:
            errors.append(
                f"⚠️ 第 {h['line_num']} 行：[CHILD_TOO_SMALL] leaf 內文僅 {h['content_tokens']} tokens（建議 ≥{MIN_LEAF_TOKENS}），"
                f"可能是不完整段落、純跳轉提示或 ingest 殘片；若內容已完整自洽可忽略 ➔ {h['clean_line']}"
            )

    return errors

# --- 2. 註冊 Django Admin Action ---
@admin.action(description='(RAG) 2. 檢查 Markdown 層級與標籤漏洞')
def check_markdown_hierarchy_action(modeladmin, request, queryset):
    """
    接收勾選的 queryset，針對特定欄位進行檢查，並輸出結果。
    """
    success_count = 0
    error_logs = []

    for obj in queryset:
        # ⚠️ 注意：請將 'content' 換成你 Model 中實際存放 Markdown 的欄位名稱
        # ⚠️ 請將 'title' 換成你用來識別該筆資料的名稱
        markdown_text = getattr(obj, 'processed_text', '') 
        document_name = getattr(obj, 'title', f"ID: {obj.id}")
        
        if not markdown_text:
            continue

        # 執行驗證
        errors = validate_markdown_hierarchy(markdown_text)

        if errors:
            error_html = f"<strong>【{document_name}】發現 {len(errors)} 個錯誤：</strong><br>"
            error_html += "<br>".join(errors)
            error_logs.append(error_html)
        else:
            obj.status = "validated"
            obj.save(update_fields=["status", "updated_at"])
            success_count += 1

    # --- 3. 將結果顯示在 Django Admin 上方 ---
    if success_count > 0:
        modeladmin.message_user(
            request, 
            f"✅ 檢查完畢：共有 {success_count} 筆文件層級完全正確！", 
            messages.SUCCESS
        )

    if error_logs:
        # 使用 mark_safe 讓 Django 渲染 HTML (換行效果)
        for error_msg in error_logs:
            modeladmin.message_user(
                request, 
                mark_safe(error_msg), 
                messages.ERROR
            )
    

# --- whole_context 的 bracket 檢查 ---
# whole_context 是人工調整區，這三種標記全部靠手打，漏一個收尾就會讓後面整段規則書
# 被 LLM 當成圖表資料或註記。這裡只驗 bracket 配對，不碰層級/標籤（那是 processed_text 的事）。
WHOLE_CONTEXT_BLOCK_MARKERS = ("image data", "context note")


def validate_whole_context_brackets(text: str) -> list[str]:
    """
    檢查 whole_context 的 markdown：

    1. 三種標記的 bracket 是否配對：
      - `[image: description]`（單行，必須同行收尾）
      - `[image data: ...]` … `[/image data]`（成對區塊）
      - `[context note: ...]` … `[/context note]`（成對區塊）
    2. 章節標題一律 `##` 起跳，不可用單一 `#`——單 `#` 在下游（flowchart /
       script / rulesbot）會跟章節標題混在一起，分不出哪個才是段落層級。

    回傳 ❌/⚠️ 開頭的訊息清單；空清單代表通過。
    """
    errors: list[str] = []
    if not text:
        return errors

    # `[image: ...]` 必須在同一行收尾
    image_open_re = re.compile(r"\[image\s*:", re.IGNORECASE)
    image_pair_re = re.compile(r"\[image\s*:[^\]\n]*\]", re.IGNORECASE)

    # 成對區塊：開啟標記本身也要在同一行收尾（例：`[image data: 棋盤格]`）
    block_open_re = {
        m: re.compile(r"\[" + m.replace(" ", r"\s+") + r"\s*:", re.IGNORECASE)
        for m in WHOLE_CONTEXT_BLOCK_MARKERS
    }
    block_open_pair_re = {
        m: re.compile(r"\[" + m.replace(" ", r"\s+") + r"\s*:[^\]\n]*\]", re.IGNORECASE)
        for m in WHOLE_CONTEXT_BLOCK_MARKERS
    }
    block_close_re = {
        m: re.compile(r"\[/\s*" + m.replace(" ", r"\s+") + r"\s*\]", re.IGNORECASE)
        for m in WHOLE_CONTEXT_BLOCK_MARKERS
    }
    # 單一 `#` 的標題：whole_context 的頂層章節一律 `##`
    single_hash_re = re.compile(r"^\s{0,3}#(?!#)[ \t]+\S")
    # `# of players` 的 `#` 讀作 "number of"，是內文；報 ⚠️ 讓人自己判斷，不當錯誤
    hash_count_idiom_re = re.compile(r"^\s{0,3}#[ \t]+of\b", re.IGNORECASE)

    # 缺 `]` 的殘缺收尾，例如 `[/image data`
    broken_close_re = {
        m: re.compile(r"\[/\s*" + m.replace(" ", r"\s+") + r"(?!\s*\])", re.IGNORECASE)
        for m in WHOLE_CONTEXT_BLOCK_MARKERS
    }

    def _snippet(line: str) -> str:
        clean = line.strip()
        return clean if len(clean) <= 120 else clean[:120] + "…"

    # 目前開啟中的區塊：(marker, 起始行號)；不允許巢狀
    open_block: tuple[str, int] | None = None

    for line_num, line in enumerate(text.splitlines(), start=1):
        # 0. 單一 `#` 標題：應該寫成 `##`
        if single_hash_re.match(line):
            if hash_count_idiom_re.match(line):
                errors.append(
                    f"⚠️ 第 {line_num} 行：行首單一 `#`，看起來是 `# of ...`（數量）的"
                    f"內文用法，已原樣保留；若這其實是章節標題請自行改成 `##` "
                    f"➔ {_snippet(line)}"
                )
            else:
                errors.append(
                    f"❌ 第 {line_num} 行：標題用了單一 `#`，whole_context 的章節標題一律 "
                    f"`##` 起跳 ➔ {_snippet(line)}"
                )

        # 1. `[image:` 開啟數必須等於同行完整配對數
        n_image_open = len(image_open_re.findall(line))
        if n_image_open > len(image_pair_re.findall(line)):
            errors.append(
                f"❌ 第 {line_num} 行：`[image:` 缺少收尾 `]`（必須在同一行閉合）➔ {_snippet(line)}"
            )

        for marker in WHOLE_CONTEXT_BLOCK_MARKERS:
            close_hits = len(block_close_re[marker].findall(line))

            # 7. 殘缺收尾（`[/image data` 少了 `]`）
            if len(broken_close_re[marker].findall(line)) > 0:
                errors.append(
                    f"⚠️ 第 {line_num} 行：疑似寫壞的收尾標記，應為 `[/{marker}]` ➔ {_snippet(line)}"
                )

            # 5/6. 收尾標記
            if close_hits:
                if open_block is None:
                    errors.append(
                        f"❌ 第 {line_num} 行：孤兒 `[/{marker}]`，前面沒有對應的 `[{marker}:` ➔ {_snippet(line)}"
                    )
                elif open_block[0] != marker:
                    errors.append(
                        f"❌ 第 {line_num} 行：`[/{marker}]` 與第 {open_block[1]} 行開啟的 "
                        f"`[{open_block[0]}:` 不匹配 ➔ {_snippet(line)}"
                    )
                    open_block = None
                else:
                    open_block = None

            # 2/4. 開啟標記
            if block_open_re[marker].search(line):
                if not block_open_pair_re[marker].search(line):
                    errors.append(
                        f"❌ 第 {line_num} 行：`[{marker}:` 開頭標記缺少收尾 `]`"
                        f"（開頭標記必須在同一行閉合）➔ {_snippet(line)}"
                    )
                if open_block is not None:
                    errors.append(
                        f"❌ 第 {line_num} 行：上一個 `[{open_block[0]}:` 區塊（第 {open_block[1]} 行）"
                        f"尚未關閉就再次開啟 `[{marker}:` ➔ {_snippet(line)}"
                    )
                open_block = (marker, line_num)

    # 3. 掃到檔尾仍有未關閉的區塊
    if open_block is not None:
        marker, start_line = open_block
        errors.append(
            f"❌ 第 {start_line} 行：`[{marker}:` 區塊未以 `[/{marker}]` 結束（直到文末都沒有收尾）"
        )

    return errors


@admin.action(description='💫2️⃣檢查 whole context 的 markdown')
def check_whole_context_brackets_action(modeladmin, request, queryset):
    """檢查 whole_context 的 bracket 配對；純唯讀，不寫任何欄位。"""
    success_count = 0
    skipped = 0
    error_logs = []

    for obj in queryset:
        whole_context = getattr(obj, 'whole_context', '') or ''
        document_name = getattr(obj, 'title', None) or f"ID: {obj.id}"

        if not whole_context.strip():
            skipped += 1
            continue

        errors = validate_whole_context_brackets(whole_context)

        if errors:
            error_html = f"<strong>【{document_name}】發現 {len(errors)} 個問題：</strong><br>"
            error_html += "<br>".join(errors)
            error_logs.append(error_html)
        else:
            success_count += 1

    if success_count > 0:
        modeladmin.message_user(
            request,
            f"✅ 檢查完畢：共有 {success_count} 筆 whole_context 的 bracket 與標題層級完全正確！",
            messages.SUCCESS
        )

    if skipped > 0:
        modeladmin.message_user(
            request,
            f"⏭️ 有 {skipped} 筆 whole_context 為空，已略過。",
            messages.WARNING
        )

    if error_logs:
        for error_msg in error_logs:
            modeladmin.message_user(
                request,
                mark_safe(error_msg),
                messages.ERROR
            )


class FlowchartPublishedFilter(admin.SimpleListFilter):
    title = "Flowchart Published"
    parameter_name = "flowchart_published"

    def lookups(self, request, model_admin):
        return [
            ("all", "✅ All published"),
            ("partial", "⚠️ Partially published"),
            ("none", "❌ None published"),
            ("no_flowcharts", "— No flowcharts"),
        ]

    def queryset(self, request, queryset):
        # 公開與否看 FlowchartPublication.is_live（見 game/flowchart_review.py）
        published_charts = RulebookFlowchart.objects.published()
        has_published = published_charts.values("rulebook_id")
        has_unpublished = (
            RulebookFlowchart.objects.exclude(pk__in=published_charts.values("pk"))
            .values("rulebook_id")
        )
        if self.value() == "all":
            return queryset.filter(flowcharts__isnull=False).exclude(id__in=has_unpublished).distinct()
        if self.value() == "partial":
            return queryset.filter(id__in=has_published).filter(id__in=has_unpublished).distinct()
        if self.value() == "none":
            return queryset.filter(flowcharts__isnull=False).exclude(id__in=has_published).distinct()
        if self.value() == "no_flowcharts":
            return queryset.filter(flowcharts__isnull=True)
        return queryset


class WholeContextFilter(admin.SimpleListFilter):
    """whole_context 是人工填的全文問答素材，用這個 filter 快速找出還沒填的。"""

    title = "Whole Context"
    parameter_name = "whole_context_state"

    def lookups(self, request, model_admin):
        return [
            ("has", "✅ 有內容"),
            ("empty", "❌ 空值"),
        ]

    def queryset(self, request, queryset):
        from django.db.models import Q

        # blank=True 的 TextField 正常是 ""，舊資料還是可能是 NULL，兩種都當空值。
        empty = Q(whole_context="") | Q(whole_context__isnull=True)
        if self.value() == "has":
            return queryset.exclude(empty)
        if self.value() == "empty":
            return queryset.filter(empty)
        return queryset


@admin.register(Rulebook)
class RulebookAdmin(admin.ModelAdmin):
    list_display = (
        "title", "language", "edition_summary", "file_link", "has_source_url",
        # "status",
        "last_error_display",
        "token_summary",
        "content_languages_display",
        "flowchart_published_status",
        "updated_at",
    )
    list_select_related = ("edition", "edition__game", "language")
    ordering = ("-edition__release_year", "edition__game__max_playtime", "edition__game__min_playtime", "edition__age")
    list_filter = (
        "language",
        "source_url_status",
        WholeContextFilter,
        FlowchartPublishedFilter,
    )
    search_fields = (
        "title",
        "edition__name",
        "edition__game__canonical_name",
        "edition__roles__entity__name",
    )
    readonly_fields = (
        "id", "created_at", "updated_at", "content_hash", "last_error", "chat_bundle_preview",
        "source_url_status", "source_url_fail_count", "source_url_checked_at",
    )
    autocomplete_fields = ("edition", "language")
    formfield_overrides = {
        models.JSONField: {"widget": forms.Textarea(attrs={"rows": 1, "style": "font-family: monospace;"})},
    }

    def get_queryset(self, request):
        # Whole Tokens 欄要能排序，先讓資料庫算好 whole_context 的字元數
        from django.db.models.functions import Length
        return super().get_queryset(request).annotate(
            whole_context_len=Length("whole_context")
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "edition" and "widget" not in kwargs:
            # 使用專屬 autocomplete widget，讓下拉選項顯示 release year
            kwargs["widget"] = EditionYearAutocompleteSelect(db_field, self.admin_site)
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "edition" and formfield is not None:
            # 讓已選取的 edition 顯示其 release year（與下拉選項一致）
            def label_with_year(obj):
                if obj.release_year:
                    return f"{obj} ({obj.release_year})"
                return str(obj)
            formfield.label_from_instance = label_with_year
        return formfield

    actions = [
        extract_rulebooks_whole_context,
        check_whole_context_brackets_action,
        "compute_pdf_info",
        generate_flowcharts_action,
        "create_empty_flowchart",
        extract_and_clean_rulebooks_llamaparse,
        extract_rulebooks_pymupdf,
        check_markdown_hierarchy_action,
        run_rag_ingest_full,
        index_to_qdrant,
        diagnose_qdrant,
        delete_from_qdrant,
    ]

    @admin.action(description="📝 建立空白 Flowchart（不生成內容）")
    def create_empty_flowchart(self, request, queryset):
        # 只建一筆空殼（ruleset=basic，其餘欄位用預設值），之後到 Flowchart 頁手動編輯。
        # (rulebook, ruleset) 有唯一限制，已存在就跳過。
        created = skipped = 0
        for rb in queryset:
            _, was_created = RulebookFlowchart.objects.get_or_create(
                rulebook=rb, ruleset="basic",
                defaults={"edition_id": rb.edition_id},
            )
            if was_created:
                created += 1
            else:
                skipped += 1
        self.message_user(
            request,
            f"已建立 {created} 筆空白 flowchart，略過 {skipped} 筆（已有 basic ruleset）。",
        )

    @admin.action(description="🔢 Compute PDF tokens & languages")
    def compute_pdf_info(self, request, queryset):
        from .tasks import _count_tokens, _detect_languages
        from .rag.rulebook_processing import extract_pages_from_pdf_bytes
        updated = skipped = 0
        for rb in queryset:
            if not rb.file:
                skipped += 1
                continue
            try:
                pdf_bytes = rb.file.read()
                pages = extract_pages_from_pdf_bytes(pdf_bytes)
                page_texts = [p["text"] for p in pages]
                full_text = "\n".join(page_texts)
                rb.pdf_token_count = _count_tokens(full_text)
                rb.content_languages = _detect_languages(page_texts)
                rb.save(update_fields=["pdf_token_count", "content_languages", "updated_at"])
                updated += 1
            except Exception as e:
                self.message_user(request, f"❌ {rb.title}: {e}", messages.ERROR)
        self.message_user(request, f"Updated {updated} rulebook(s). Skipped {skipped} (no PDF file).")

    @admin.display(description="Chat 打包預覽")
    def chat_bundle_preview(self, obj):
        """
        rulesbot 問答餵給模型的是「這個 edition + 一種語言」底下的**全部**就緒
        規則書（見 selectors.resolve_chat_bundle），不是只有這一本。這裡把各語言
        會打包成什麼樣子列出來。

        存在的理由是 Rulebook.language 有髒資料：scraper 對不上語言時會退回 en，
        於是 en 那組可能混進瑞典文、波蘭文的 PDF。光看單一 rulebook 的編輯頁看
        不出這件事，要整組排在一起才會發現。
        """
        if not obj.pk or not obj.edition_id:
            return "—"

        from collections import defaultdict
        from game.selectors import _ready_for_bundle, _bundle_token_estimate

        # 與 resolve_chat_bundle 同一個 queryset（含 defer + 長度 annotation），
        # 預覽才不會為了算 token 把整個 edition 的規則書全文載進來
        ready = list(
            _ready_for_bundle()
            .filter(edition_id=obj.edition_id)
            .order_by("created_at", "id")
        )
        if not ready:
            return format_html(
                '<span style="color:#dc3545;">這個 edition 底下沒有任何就緒的規則書'
                '（whole_context 為空），rulesbot 目前不會用到它。</span>'
            )

        groups = defaultdict(list)
        for rb in ready:
            groups[rb.language.name if rb.language else "—"].append(rb)

        rows = []
        for lang, rbs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            total = sum(_bundle_token_estimate(rb) for rb in rbs)
            items = "".join(
                '<li>{}Ref {} — {} <span style="opacity:.6;">(~{:,} tokens)</span></li>'.format(
                    "<b>» </b>" if rb.pk == obj.pk else "",
                    i, rb.title, _bundle_token_estimate(rb),
                )
                for i, rb in enumerate(rbs, start=1)
            )
            warn = (
                ' <span style="color:#fd7e14;">⚠️ 同語言多本，確認這些真的是不同文件'
                '（主規則書／擴充／FAQ），不是同一份的其他語言版本</span>'
                if len(rbs) > 1 else ""
            )
            rows.append(
                "<div style='margin-bottom:8px;'><b>{}</b> — {} 本，合計 ~{:,} tokens{}"
                "<ul style='margin:2px 0 0 18px;'>{}</ul></div>".format(
                    lang, len(rbs), total, warn, items,
                )
            )

        return format_html(
            "<div style='font-size:12px;'>問答會依使用者介面語言挑一組（介面語言 → "
            "英文 → 本數最多的語言），整組一起進 prompt。<hr style='margin:6px 0;'>{}</div>",
            mark_safe("".join(rows)),
        )

    @admin.display(description="Error")
    def last_error_display(self, obj):
        if not obj.last_error:
            return "—"
        return format_html(
            '<span style="color: #dc3545;" title="{}">{}</span>',
            obj.last_error, obj.last_error[:80],
        )

    @admin.display(description="Source URL", ordering="source_url")
    def has_source_url(self, obj):
        if not obj.source_url:
            return "-"
        if obj.source_url_status == "broken":
            return format_html(
                '<a href="{}" target="_blank" rel="noopener" title="Broken: {}" '
                'style="text-decoration:none;color:#cf1322;">✘</a>',
                obj.source_url,
                obj.source_url,
            )
        return format_html(
            '<a href="{}" target="_blank" rel="noopener" title="{}" '
            'style="text-decoration:none;">✔</a>',
            obj.source_url,
            obj.source_url,
        )

    def save_model(self, request, obj, form, change):
        # 網址改了，舊的檢查結果就不算數
        if change and "source_url" in form.changed_data:
            obj.source_url_status = "unknown"
            obj.source_url_fail_count = 0
            obj.source_url_checked_at = None
        super().save_model(request, obj, form, change)

    @admin.display(description="PDF")
    def file_link(self, obj):
        """列表只放一個可點的圖示；完整路徑/檔名太長，會把整列擠爆。"""
        if not obj.file:
            return "—"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener" title="{}" '
            'style="font-size:16px;text-decoration:none;">\U0001F4C4</a>',
            obj.file.url,
            obj.file.name,
        )

    @admin.display(description="PDF Lang")
    def content_languages_display(self, obj):
        langs = obj.content_languages
        if not langs:
            return "-"
        return ", ".join(langs)

    @admin.display(description="Flowchart Published")
    def flowchart_published_status(self, obj):
        flowcharts = obj.flowcharts.all()
        total = flowcharts.count()
        if total == 0:
            return "—"
        published = flowcharts.published().count()
        if published == 0:
            return format_html('<span style="color:#dc3545;">❌ 0/{}</span>', total)
        if published == total:
            return format_html('<span style="color:green;">✅ {}/{}</span>', published, total)
        return format_html('<span style="color:#fd7e14;">⚠️ {}/{}</span>', published, total)

    @admin.display(description="Token (whole/PDF)", ordering="whole_context_len")
    def token_summary(self, obj):
        """
        「實際餵給模型的量 / 這份 PDF 原本有多少」並排。

        左邊 whole_context 是現算的（人工修過就會變，存欄位一定會過期），右邊
        pdf_token_count 是 parse 當下寫進 DB 的。兩邊都用 cl100k，數字可以直接
        對比：左邊遠小於右邊通常代表全文擷取只成功了一部分。

        排序用 get_queryset() 標的字元數（whole_context_len），不是顯示的 token
        數——token 化只能在 Python 端算，沒辦法讓資料庫 ORDER BY。同一套 tokenizer
        下字元數與 token 數單調相關，長短順序足夠用；相鄰兩本長度接近時偶爾會與
        token 數的嚴格順序差一名。
        """
        from .tasks import _count_tokens
        text = obj.whole_context or ""
        whole = f"{_count_tokens(text):,}" if text else "-"
        pdf = f"{obj.pdf_token_count:,}" if obj.pdf_token_count else "-"
        return f"{whole} / {pdf}"

    @admin.display(description="Edition (age | playtime | year)", ordering="edition__release_year")
    def edition_summary(self, obj):
        return " | ".join([
            self._edition_age(obj),
            self._package_playtime(obj),
            self._edition_release_year(obj),
        ])

    def _edition_age(self, obj):
        if obj.edition and obj.edition.age is not None:
            return f"{obj.edition.age}"
        return "-"

    def _package_playtime(self, obj):
        game = getattr(obj.edition, "game", None)
        if not game:
            return "-"
        min_time = game.min_playtime
        max_time = game.max_playtime
        if min_time is None and max_time is None:
            return "-"
        if min_time is None:
            return f"≤{max_time} min"
        if max_time is None:
            return f"≥{min_time} min"
        return f"{min_time} - {max_time} min"

    def _edition_release_year(self, obj):
        if obj.edition and obj.edition.release_year:
            return str(obj.edition.release_year)
        return "-"

    @admin.display(description="Nodes")
    def chunk_count(self, obj):
        count = obj.rulebook_nodes.count()
        if count > 0:
            synced = obj.rulebook_nodes.filter(
                vector_sync_status="synced"
            ).count()
            return format_html(
                '<span title="Synced: {}">{} ({}✓)</span>',
                synced, count, synced
            )
        return "0"
    
    fieldsets = (
        ("基本資訊", {
            "fields": (
                "edition", "title", "language",
                "source_url", "source_url_status", "source_url_checked_at", "file"
            )
        }),
        ("處理狀態", {
            "fields": (
                "status", "pdf_token_count", "content_languages",
                "chat_bundle_preview",
            )
        }),
        ("文字內容", {
            "description": GRID_COORDINATE_HINT,
            "fields": (
                "extracted_text", "processed_text", "whole_context"
            ),
        }),
        ("系統資訊", {
            "fields": (
                "id", "content_hash", "created_at", "updated_at"
            ),
            "classes": ("collapse",),
        }),
    )
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "rag-test/",
                self.admin_site.admin_view(self.rag_test_view),
                name="game_rulebook_rag_test",
            ),
            path(
                "classify-question-test/",
                self.admin_site.admin_view(self.classify_question_test_view),
                name="game_classify_question_test",
            ),
        ]
        return custom_urls + urls

    def classify_question_test_view(self, request):
        """
        Staff 小工具：輸入一句問題，並排跑兩種分類器，顯示分到哪一類與各自實際
        花了多少 token。純測試用途，不寫 DB。

        - 七類分類器：正式流程（chat_views.py）在用的那個，rules + 5 種 reasoning
          子類 + other。
        - 簡化三類分類器：實驗性的，scenario / rules / other，決策順序固定，
          純粹依「有沒有描述遊戲情境」「有沒有提到桌遊常用詞」判斷，不看規則書
          也不看對話歷史。目前只在這個工具跑，沒有接進正式流程。
        """
        from game.rag.rag_service import get_rag_service

        question = None
        result = None
        simple_result = None
        error = None

        if request.method == "POST":
            form = ClassifyQuestionTestForm(request.POST)
            if form.is_valid():
                question = form.cleaned_data["question"]
                svc = get_rag_service()
                try:
                    category, usage = svc._classify_question_with_usage(question)
                    result = {
                        "category": category,
                        "category_label": ChatMessage.Category(category).label
                            if category in ChatMessage.Category.values else category,
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                    }
                    simple_category, simple_usage = svc._classify_question_simple_with_usage(question)
                    simple_result = {
                        "category": simple_category,
                        "prompt_tokens": simple_usage.get("prompt_tokens"),
                        "completion_tokens": simple_usage.get("completion_tokens"),
                        "total_tokens": simple_usage.get("total_tokens"),
                    }
                except Exception as e:
                    error = str(e)
        else:
            form = ClassifyQuestionTestForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "問題分類測試",
            "form": form,
            "question": question,
            "result": result,
            "simple_result": simple_result,
            "error": error,
        }
        return render(request, "admin/game/classify_question_test.html", context)

    def rag_test_view(self, request):
        from game.rag.retriever import QdrantRetriever  # lazy：sentence-transformers/torch 僅 local

        results = None

        if request.method == "POST":
            form = RagTestForm(request.POST)
            if form.is_valid():
                rulebook = form.cleaned_data["rulebook"]
                query = form.cleaned_data["query"]
                top_k = form.cleaned_data["top_k"]

                # 只檢索該 rulebook
                q_filter = Filter(
                    must=[
                        FieldCondition(
                            key="rulebook_id",
                            match=MatchValue(value=str(rulebook.id)),
                        )
                    ]
                )

                retriever = QdrantRetriever(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_PORT,
                    collection_name=settings.QDRANT_COLLECTION_NAME,
                    model_name=settings.EMBEDDING_MODEL_NAME,
                    device=settings.EMBEDDING_DEVICE,
                    query_prefix=settings.E5_QUERY_PREFIX,  # "query: "
                    api_key=getattr(settings, "QDRANT_API_KEY", None),
                )

                results = retriever.retrieve(
                    query,
                    top_k=top_k,
                    qdrant_filter=q_filter,
                )

                # 額外：幫每筆結果加上「連到 RulebookNode 的 admin 連結」
                # 前提：node_id 是 RulebookNode UUID（你 payload 看起來是）
                for r in results:
                    node_id = None
                    if r.payload:
                        node_id = r.payload.get("node_id")
                    if node_id:
                        r.payload["admin_node_url"] = reverse(
                            "admin:game_rulebooknode_change",
                            args=[node_id],
                        )

        else:
            form = RagTestForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "RAG Retrieval Test",
            "form": form,
            "results": results,
        }
        return render(request, "admin/game/rag_test.html", context)

@admin.register(RulebookQA)
class RulebookQAAdmin(admin.ModelAdmin):
    list_display = (
        "id", "question_short", "rulebook", 
        "language", "sync_status_colored", 
        "vector_synced_at", "updated_at"
    )
    list_filter = (
        "vector_sync_status", "language", 
        "rulebook", "embedding_model"
    )
    search_fields = (
        "question", "answer", "note", 
        "rulebook__title", "game__canonical_name"
    )
    autocomplete_fields = ("rulebook", "language", "source_message")
    readonly_fields = (
        "id", "game", "edition", "vector_point_id", 
        "vector_synced_at", "created_at", "updated_at"
    )

    fieldsets = (
        ("基本內容", {
            "fields": (
                "id", "rulebook", ("game", "edition"), 
                "language", "source_message"
            )
        }),
        ("Q&A 內容", {
            "fields": ("question", "answer", "note")
        }),
        ("向量同步狀態", {
            "fields": (
                "vector_sync_status", "vector_point_id", 
                "vector_collection", "embedding_model", 
                "embedding_version", "vector_synced_at", 
                "vector_last_error"
            ),
            "classes": ("collapse",),
        }),
    )

    def changelist_view(self, request, extra_context=None):
        messages.info(
            request,
            "💡 有 Pending 的資料時，請到 Rulebook 執行「🔧 手動改動節點後同步 (Smart Sync)」"
        )
        return super().changelist_view(request, extra_context=extra_context)

    def question_short(self, obj):
        return obj.question[:50] + "..." if len(obj.question) > 50 else obj.question
    question_short.short_description = "Question"

    @admin.display(description="同步狀態")
    def sync_status_colored(self, obj):
        colors = {
            "pending": "#FFA500",   # 橙色
            "synced": "#28A745",    # 綠色
            "failed": "#DC3545",    # 紅色
        }
        color = colors.get(obj.vector_sync_status, "#6C757D")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_vector_sync_status_display()
        )



class ChatMessageInline(admin.TabularInline):
    """在 ChatSession 頁面內，直接顯示所有對話訊息"""
    model = ChatMessage
    extra = 0
    ordering = ("created_at",)
    readonly_fields = ("role", "content_display", "feedback_display", "sources_display", "prompt_tokens", "completion_tokens", "total_tokens", "created_at")
    fields = ("role", "content_display", "feedback_display", "sources_display", "prompt_tokens", "completion_tokens", "total_tokens", "created_at")
    
    # 不允許在 admin 新增/刪除訊息
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="內容")
    def content_display(self, obj):
        """訊息內容，過長時截斷處理"""
        content = obj.content
        if len(content) > 300:
            return content[:300] + "..."
        return content

    @admin.display(description="反饋")
    def feedback_display(self, obj):
        """顯示用戶的反饋內容"""
        from .models import ChatMessage
        if obj.role == "user":
            return "-"
        
        icon = "-"
        if obj.feedback == ChatMessage.Feedback.LIKE:
            icon = "✅"
        elif obj.feedback == ChatMessage.Feedback.DISLIKE:
            icon = "👎"
        
        if obj.feedback_text:
            return format_html('{} <br><small style="color:#666">{}</small>', icon, obj.feedback_text)
        return icon

    @admin.display(description="來源")
    def sources_display(self, obj):
        """格式化顯示 sources"""
        if not obj.sources:
            return "-"
        
        # sources 是 list，顯示數量和摘要
        if isinstance(obj.sources, list):
            count = len(obj.sources)
            if count == 0:
                return "-"
            
            # 顯示前 2 個來源的摘要
            preview_items = []
            for src in obj.sources[:2]:
                if isinstance(src, dict):
                    # 根據你的 sources 結構調整這裡
                    text = src.get("text", src.get("content", str(src)))[:50]
                    preview_items.append(f"• {text}...")
                else:
                    preview_items.append(f"• {str(src)[:50]}...")
            
            preview = "<br>".join(preview_items)
            if count > 2:
                preview += f"<br><em>...還有 {count - 2} 個來源</em>"
            
            return format_html(preview)
        
        return str(obj.sources)[:100]


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    """對話 Session 的 Admin 介面"""
    
    list_display = (
        "short_id",
        "edition_link",
        "rulebook_link",
        "user",
        "user_name",
        "first_question_preview",
        "message_count",
        "deleted_status",
        "created_at",
    )

    list_filter = (
        "edition",
        "user",
        "rulebook",
        "created_at",
        ("deleted_at", admin.EmptyFieldListFilter),
    )

    search_fields = (
        "user__username",
        "user_name",
        "messages__content",  # 可搜尋對話內容
    )

    readonly_fields = (
        "id",
        "edition",
        "rulebook",
        "user",
        "user_name",
        "created_at",
        "updated_at",
        "deleted_at",
        "full_conversation",
    )

    fields = (
        "id",
        "edition",
        "rulebook",
        "user",
        "user_name",
        "created_at",
        "updated_at",
        "deleted_at",
        "full_conversation",
    )
    
    inlines = [ChatMessageInline]
    
    ordering = ("-created_at",)
    
    list_per_page = 30

    # === Display Methods ===
    
    @admin.display(description="ID")
    def short_id(self, obj):
        """只顯示 UUID 前 8 碼"""
        return str(obj.id)[:8]

    @admin.display(description="已清除？", boolean=False)
    def deleted_status(self, obj):
        """使用者按「清除對話」是 soft delete；這裡讓 admin 看得出哪些是被清除的。"""
        if not obj.deleted_at:
            return "—"
        return format_html(
            '<span style="color:#dc3545;" title="{}">🗑 已清除</span>',
            obj.deleted_at.strftime("%Y-%m-%d %H:%M"),
        )

    @admin.display(description="Edition")
    def edition_link(self, obj):
        if not obj.edition:
            return "-"
        url = reverse("admin:game_edition_change", args=[obj.edition.id])
        return format_html('<a href="{}">{}</a>', url, obj.edition)

    @admin.display(description="Rulebook")
    def rulebook_link(self, obj):
        """可點擊的規則書連結"""
        if not obj.rulebook:
            return "-"
        url = reverse("admin:game_rulebook_change", args=[obj.rulebook.id])
        return format_html('<a href="{}">{}</a>', url, obj.rulebook.title)

    @admin.display(description="首問預覽")
    def first_question_preview(self, obj):
        """顯示第一個 user 問題的前 50 字"""
        first_msg = obj.messages.filter(role="user").order_by("created_at").first()
        if first_msg:
            content = first_msg.content
            if len(content) > 50:
                return content[:50] + "..."
            return content
        return "-"

    @admin.display(description="訊息數")
    def message_count(self, obj):
        """顯示這場對話有幾則訊息"""
        count = obj.messages.count()
        # 用顏色區分：單輪 vs 多輪
        if count <= 2:
            return format_html('<span style="color: green;">{}</span>', count)
        elif count <= 6:
            return format_html('<span style="color: orange;">{}</span>', count)
        else:
            return format_html('<span style="color: red;">{}</span>', count)

    @admin.display(description="完整對話")
    def full_conversation(self, obj):
        """在詳情頁顯示完整對話（格式化）"""
        messages = obj.messages.order_by("created_at")
        
        if not messages.exists():
            return "（無訊息）"
        
        html_parts = ['<div style="font-family: monospace; line-height: 1.6;">']
        
        for msg in messages:
            if msg.role == "user":
                color = "#1a73e8"
                label = "👤 User"
            else:
                color = "#34a853"
                label = "🤖 Assistant"
            
            # 處理換行
            content_html = msg.content.replace("\n", "<br>")
            
            # 加入反饋資訊
            feedback_html = ""
            if msg.role == "assistant" and msg.feedback != msg.Feedback.NONE:
                icon = "✅" if msg.feedback == msg.Feedback.LIKE else "👎"
                text = f' <span style="font-size: 0.9em; color: #666;">({msg.feedback_text})</span>' if msg.feedback_text else ""
                feedback_html = f'<div style="margin-top: 8px; font-size: 1.2em;">{icon}{text}</div>'

            html_parts.append(
                f'<div style="margin-bottom: 12px; padding: 8px; '
                f'border-left: 3px solid {color}; background: #f8f9fa;">'
                f'<strong style="color: {color};">{label}</strong><br>'
                f'{content_html}'
                f'{feedback_html}'
                f'</div>'
            )
        
        html_parts.append('</div>')
        
        return mark_safe("".join(html_parts))


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """
    單獨的 ChatMessage Admin
    主要用於：搜尋特定內容、批量檢視
    """
    
    list_display = (
        "id_short",
        "short_session_id",
        "role_display",
        "mode",
        "category_raw",
        "content_preview",
        "feedback_icon",
        "token_usage",
        "has_sources",
        "session_deleted",
        "created_at",
    )

    list_display_links = ("id_short", "content_preview")

    list_filter = (
        "mode",
        "category",
        "role",
        "feedback",
        "session__rulebook",
        "created_at",
    )
    
    search_fields = (
        "content",
    )
    
    readonly_fields = (
        "session",
        "role",
        "mode",
        "category",
        "content",
        "feedback",
        "feedback_text",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cached_tokens",
        "sources_formatted",
        "created_at",
    )
    
    ordering = ("-created_at",)

    list_per_page = 50

    # short_session_id 與 session_deleted 都要讀 obj.session；沒有這行每頁 50 筆
    # 就是 50 次額外查詢
    list_select_related = ("session",)

    @admin.display(description="ID")
    def id_short(self, obj):
        return str(obj.id)[:8]

    @admin.display(description="Session")
    def short_session_id(self, obj):
        """Session ID 前 8 碼，可點擊連往 Session"""
        from django.urls import reverse
        url = reverse("admin:game_chatsession_change", args=[obj.session.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.session.id)[:8])

    @admin.display(description="角色")
    def role_display(self, obj):
        """用 emoji 顯示角色"""
        if obj.role == "user":
            return "👤 User"
        if obj.role.startswith("Gemini"):
            return f"🧔🏼 {obj.role}"
        if obj.role.startswith("OpenAI"):
            return f"👩🏼‍🦰 {obj.role}"
        if obj.role.startswith("Claude"):
            return f"🎅🏼 {obj.role}"
        return f"🤖 {obj.role}"

    @admin.display(description="分類", ordering="category")
    def category_raw(self, obj):
        """直接顯示 choices 的原始值（rules/scenario/other），不要 label 描述文字。"""
        return obj.category or "-"

    @admin.display(description="Session 已清除？")
    def session_deleted(self, obj):
        if not obj.session.deleted_at:
            return "—"
        return format_html(
            '<span style="color:#dc3545;" title="{}">🗑 已清除</span>',
            obj.session.deleted_at.strftime("%Y-%m-%d %H:%M"),
        )

    @admin.display(description="內容預覽")
    def content_preview(self, obj):
        """內容前 80 字"""
        if len(obj.content) > 80:
            return obj.content[:80] + "..."
        return obj.content

    @admin.display(description="反饋")
    def feedback_icon(self, obj):
        if obj.role == "user":
            return "-"
        
        # 這裡直接從位元組或模型類別判斷
        from .models import ChatMessage
        
        if obj.feedback == ChatMessage.Feedback.LIKE:
            return "✅"
        elif obj.feedback == ChatMessage.Feedback.DISLIKE:
            return "👎"
        
        return "⚪" # 使用灰色圓圈表示已有欄位但尚無反饋

    @admin.display(description="有來源", boolean=True)
    def has_sources(self, obj):
        """是否有 sources"""
        return bool(obj.sources and len(obj.sources) > 0)

    @admin.display(description="來源詳情")
    def sources_formatted(self, obj):
        """詳情頁：完整顯示 sources（JSON 格式化）"""
        if not obj.sources:
            return "-"
        
        try:
            formatted = json.dumps(obj.sources, indent=2, ensure_ascii=False)
            return format_html(
                '<pre style="background: #f5f5f5; padding: 10px; '
                'overflow-x: auto; max-width: 800px;">{}</pre>',
                formatted
            )
        except:
            return str(obj.sources)
    @admin.display(description='Tokens (P/C/T)')
    def token_usage(self, obj):
        if obj.total_tokens:
            base = f'{obj.prompt_tokens} / {obj.completion_tokens} / {obj.total_tokens}'
            if obj.cached_tokens:
                pct = round(obj.cached_tokens * 100 / obj.prompt_tokens) if obj.prompt_tokens else 0
                return f'{base}  (cached {obj.cached_tokens}, {pct}%)'
            return base
        return '-'


# ---------------------------------------------------------------------------
# Collection & Scraping Admins
# ---------------------------------------------------------------------------

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("member", "edition", "preference", "updated_at")
    list_filter = ("preference",)
    search_fields = ("member__id__username", "edition__name", "edition__game__canonical_name")
    raw_id_fields = ("member", "edition")


class ScrapedProductInline(admin.TabularInline):
    model = ScrapedProduct
    extra = 0
    show_change_link = True
    fields = ("status", "reviewed_by", "reviewed_at")
    readonly_fields = ("reviewed_by", "reviewed_at", "created_at")


class ScrapeLogCompanyFilter(admin.SimpleListFilter):
    title = '來源公司'
    parameter_name = 'publisher'

    def lookups(self, request, model_admin):
        from .models import Entity
        entities = Entity.objects.filter(entity_type='company').order_by('name')
        return [(e.id, e.name) for e in entities]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(publisher_id=self.value())
        return queryset


@admin.register(ScrapeLog)
class ScrapeLogAdmin(admin.ModelAdmin):
    list_display = ("publisher", "start_at", "finish_at", "qty", "triggered_by")
    list_filter = (ScrapeLogCompanyFilter, "start_at")
    search_fields = ("publisher__name", "logs")
    raw_id_fields = ("publisher", "triggered_by")
    inlines = [ScrapedProductInline]


# ---------------------------------------------------------------------------
# ScrapedProduct Import – Form
# ---------------------------------------------------------------------------

class ScrapedImportForm(forms.Form):
    from translation.models import Tribe, Region
    from commerce.models import Currency
    language = forms.ModelChoiceField(
        queryset=None,  # set in __init__
        label="語言",
        required=True,
    )
    publisher_entity = forms.ModelChoiceField(
        queryset=Entity.objects.filter(entity_type="company").order_by("name"),
        label="出版商 Entity（僅 entity_type=company）",
        required=False,
    )
    is_primary = forms.BooleanField(
        required=False,
        initial=True,
        label="設為 Primary Edition",
    )
    currency = forms.ModelChoiceField(
        queryset=None,
        label="MSRP Currency（可選，覆寫 scraped 資料）",
        required=False,
    )
    region = forms.ModelChoiceField(
        queryset=None,
        label="Region（可選，覆寫 scraped 資料）",
        required=False,
    )
    packaging_languages = forms.ModelMultipleChoiceField(
        queryset=None,
        label="Packaging Languages（可選，覆寫 scraped 資料）",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from translation.models import Tribe, Region
        from commerce.models import Currency
        self.fields["language"].queryset = Tribe.objects.all().order_by("language")
        self.fields["packaging_languages"].queryset = Tribe.objects.all().order_by("language")
        self.fields["region"].queryset = Region.objects.all().order_by("code")
        self.fields["currency"].queryset = Currency.objects.all().order_by("code")

        # 預設 Region 為 global (id=6)
        try:
            default_region = Region.objects.get(pk=6)
            self.fields["region"].initial = default_region
        except Region.DoesNotExist:
            pass

class ScrapedImportVariantForm(ScrapedImportForm):
    """匯入 Variant 用：在共用設定中多一個 GameTitle 語言選項"""
    game_title_language = forms.ModelChoiceField(
        queryset=None,
        label="GameTitle 語言（可選）",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from translation.models import Tribe
        self.fields["game_title_language"].queryset = Tribe.objects.all().order_by("language")


class ScrapedImportBGGForm(forms.Form):
    """匯入 BGG Data 用：無共用設定欄位，只需 CSRF 結構"""
    pass


# ---------------------------------------------------------------------------
# ScrapedProduct Import – Download helpers
# ---------------------------------------------------------------------------

def _download_file(url: str, timeout: int = 30):
    """下載 URL 並回傳 (filename, ContentFile)，失敗回傳 (None, None)"""
    try:
        from uuid import uuid4
        resp = http_requests.get(url, timeout=timeout, stream=True)
        resp.raise_for_status()
        # 依 URL 推斷副檔名，但檔名本身改用 uuid，避免外部原始檔名
        clean_url = url.split("?")[0]
        ext = ""
        if "." in clean_url:
            ext = "." + clean_url.rsplit(".", 1)[-1]
        filename = f"{uuid4()}{ext}"
        return filename, ContentFile(resp.content, name=filename)
    except Exception:
        return None, None


def _merge_rulebooks(nd: dict, raw_data: dict) -> list:
    """合併 normalized_data["rulebooks"] 與 raw_data 中的多種規則書欄位，以 URL 去重。

    支援 raw_data 中的鍵：rulebook_urls (list[dict])、rulebooks (list[dict])
    若 raw_data 條目是字串 URL 而非 dict，也會被收進並標記語言為空字串。
    """
    def _normalize_entry(item):
        if isinstance(item, dict):
            url = (item.get("url") or "").strip()
            lang = (item.get("language") or "").strip()
            return {"language": lang, "url": url} if url else None
        if isinstance(item, str):
            url = item.strip()
            return {"language": "", "url": url} if url else None
        return None

    nd_rulebooks_raw = nd.get("rulebooks") or []
    nd_rulebooks = []
    for item in nd_rulebooks_raw:
        entry = _normalize_entry(item)
        if entry:
            nd_rulebooks.append(entry)

    seen_urls = {rb["url"] for rb in nd_rulebooks}
    for raw_key in ("rulebook_urls", "rulebooks"):
        for item in (raw_data or {}).get(raw_key) or []:
            entry = _normalize_entry(item)
            if entry and entry["url"] not in seen_urls:
                nd_rulebooks.append(entry)
                seen_urls.add(entry["url"])
    return nd_rulebooks


# ---------------------------------------------------------------------------
# ScrapedProduct Update – Core logic
# ---------------------------------------------------------------------------

def _get_tribe_by_lang_code(lang_code: str):
    """
    根據 scraper 返回的語言代碼（如 EN, FR, DE）查找對應的 Tribe
    優先順序：
    1. 精確匹配 Tribe.language 字段（大寫、小寫）
    2. 匹配常見的語言名稱
    3. 模糊匹配 Tribe.name
    4. 若都找不到，返回 None
    """
    from translation.models import Tribe
    
    if not lang_code:
        return None
    
    lang_code_str = str(lang_code).strip()
    if not lang_code_str:
        return None
    
    lang_code_upper = lang_code_str.upper()
    
    # 試 1: 精確匹配 language 字段（大寫）
    tribe = Tribe.objects.filter(language__iexact=lang_code_upper).first()
    if tribe:
        print(f"[TRIBE] Found by language (exact upper): {lang_code_str} -> {tribe.name}")
        return tribe
    
    # 試 2: 匹配常見的語言名稱對應
    lang_name_map = {
        "EN": "English",
        "FR": "French",
        "DE": "German",
        "ES": "Spanish",
        "IT": "Italian",
        "PT": "Portuguese",
        "NL": "Dutch",
        "PL": "Polish",
        "JA": "Japanese",
        "ZH": "Chinese",
        "KO": "Korean",
        "RU": "Russian",
        "CS": "Czech",
        "HU": "Hungarian",
    }
    
    lang_name = lang_name_map.get(lang_code_upper, "")
    if lang_name:
        tribe = Tribe.objects.filter(name__iexact=lang_name).first()
        if tribe:
            print(f"[TRIBE] Found by language name: {lang_code_str} ({lang_name}) -> {tribe.name}")
            return tribe
    
    # 試 3: 若都找不到，嘗試模糊匹配 name
    tribe = Tribe.objects.filter(name__icontains=lang_code_str).first()
    if tribe:
        print(f"[TRIBE] Found by fuzzy name match: {lang_code_str} -> {tribe.name}")
        return tribe
    
    print(f"[TRIBE] No match found for language code: {lang_code_str}")
    return None


def _do_update_existing(request, products):
    """
    對每筆已有 imported_edition 的 ScrapedProduct:
      1. 更新對應的 Game/Edition 欄位
      2. 只處理 normalized_data 中有的欄位
      3. 不改變 language, publisher_entity, game_kind, currency 等結構性欄位
    """
    from django.utils import timezone
    from commerce.models import Currency
    from translation.models import Tribe, Region

    updated_count = 0
    error_count = 0
    error_msgs = []

    reviewer = getattr(request.user, "member", None) if request.user.is_authenticated else None

    for sp in products:
        nd = sp.normalized_data
        if not nd:
            error_count += 1
            error_msgs.append(f"{sp.id}: 缺少 normalized_data")
            continue

        name = nd.get("name", "").strip()
        if not name:
            error_count += 1
            error_msgs.append(f"{sp.id}: 缺少名稱")
            continue

        try:
            edition = sp.imported_edition
            if not edition:
                error_count += 1
                error_msgs.append(f"{sp.id}: 缺少 imported_edition")
                continue

            game = edition.game

            # 1. Update Game fields
            game_updated = False
            game_fields = ["min_players", "max_players", "min_playtime", "max_playtime"]
            for field in game_fields:
                if nd.get(field) is not None:
                    current_value = getattr(game, field)
                    if current_value != nd[field]:
                        setattr(game, field, nd[field])
                        game_updated = True

            if game_updated:
                game.save()
                updated_count += 1

            # 2. Update Edition fields
            edition_updated = False
            
            # 更新 age
            if nd.get("age") is not None:
                if edition.age != nd["age"]:
                    edition.age = nd["age"]
                    edition_updated = True
            
            # 更新 summary
            if nd.get("summary") is not None:
                if edition.summary != nd["summary"]:
                    edition.summary = nd["summary"]
                    edition_updated = True

            # 更新 barcode
            barcode_val = nd.get("barcode", "__MISSING__")
            if barcode_val not in ("__MISSING__", None, ""):
                barcode_str = str(barcode_val).strip()
                if edition.barcode != barcode_str:
                    edition.barcode = barcode_str
                    edition_updated = True
            elif barcode_val in (None, "") and edition.barcode is not None:
                # 如果 normalized_data 中 barcode 為空，也清空現有的
                edition.barcode = None
                edition_updated = True

            # 更新 msrp
            if nd.get("msrp") is not None:
                if edition.msrp != nd["msrp"]:
                    edition.msrp = nd["msrp"]
                    edition_updated = True

            # 更新 msrp_currency (只從 normalized_data 讀取，不從外部參數)
            currency_code = nd.get("msrp_currency")
            if currency_code:
                cur_obj = Currency.objects.filter(code=currency_code).first()
                if cur_obj and edition.msrp_currency != cur_obj:
                    edition.msrp_currency = cur_obj
                    edition_updated = True

            # 更新 region (只從 normalized_data 讀取)
            region_code = nd.get("region_code") or nd.get("region")
            if region_code:
                region_obj = Region.objects.filter(code=region_code).first()
                if region_obj and edition.region != region_obj:
                    edition.region = region_obj
                    edition_updated = True

            # 更新 packaging_languages (只從 normalized_data 讀取)
            packaging_langs = nd.get("packaging_languages") or nd.get("packaging_language_codes")
            if packaging_langs:
                # 允許字串或 list
                if isinstance(packaging_langs, str):
                    codes = [c.strip() for c in packaging_langs.split(",") if c.strip()]
                else:
                    codes = [str(c).strip() for c in packaging_langs if str(c).strip()]
                
                tribes = []
                for code in codes:
                    tribe = Tribe.objects.filter(language=code).first() or Tribe.objects.filter(name=code).first()
                    if tribe:
                        tribes.append(tribe)
                
                if tribes:
                    edition.packaging_languages.set(tribes)

            if edition_updated:
                edition.save()
                updated_count += 1

            # 5. 更新/建立 Rulebook
            if nd.get("rulebook_url"):
                rulebook, rb_created = Rulebook.objects.get_or_create(
                    edition=edition,
                    language=edition.language,  # 使用 Edition 的 language
                    defaults={
                        "title": f"{name} Rulebook",
                        "source_url": nd["rulebook_url"],
                    },
                )
                if rb_created or not rulebook.file:
                    fname, fobj = _download_file(nd["rulebook_url"])
                    if fobj:
                        rulebook.file.save(fname, fobj, save=True)
                    if not rulebook.source_url:
                        rulebook.source_url = nd["rulebook_url"]
                        rulebook.save(update_fields=["source_url"])
                    updated_count += 1

            # 6. 更新 Designer / Artist roles
            for role_key in ("designer", "artist"):
                raw_names = nd.get(role_key, "")
                if not raw_names:
                    continue
                
                # 先清除現有的該類型 roles
                edition.roles.filter(role=role_key).delete()
                
                for person_name in raw_names.split(";"):
                    person_name = person_name.strip()
                    if not person_name:
                        continue
                    person_entity, _ = Entity.objects.get_or_create(
                        name=person_name,
                        defaults={"entity_type": "individual"},
                    )
                    EditionRole.objects.get_or_create(
                        edition=edition,
                        entity=person_entity,
                        role=role_key,
                    )

            # 7. 更新 ScrapedProduct 的審核資訊
            sp.reviewed_at = timezone.now()
            sp.reviewed_by = reviewer
            sp.status = ScrapedProduct.Status.IMPORTED
            sp.save(update_fields=["reviewed_at", "reviewed_by", "status", "updated_at"])

        except Exception as e:
            error_count += 1
            error_msgs.append(f"{sp.id}: {str(e)}")
            continue

    # 記錄錯誤訊息（如果有）
    for msg in error_msgs:
        messages.error(request, f"❌ {msg}")

    return updated_count, error_count


# ---------------------------------------------------------------------------
# ScrapedProduct Import – Core logic
# ---------------------------------------------------------------------------

def _do_import(
    request,
    products,
    language,
    publisher_entity,
    game_kind,
    is_primary,
    game=None,
    currency=None,
    region=None,
    packaging_languages=None,
    thumbnail_choice=None,
):
    """
    對每筆 ScrapedProduct:
      1. get_or_create Game (帶 kind / players / playtime)
      2. get_or_create Edition  (+ 下載 thumbnail)
      3. get_or_create EditionRole (publisher)
      4. get_or_create Rulebook    (+ 下載 rulebook PDF)
      5. 更新 ScrapedProduct.status = IMPORTED
    """
    from django.utils import timezone
    from commerce.models import Currency
    from translation.models import Tribe, Region

    created_count = 0
    skipped_count = 0
    error_msgs = []

    reviewer = getattr(request.user, "member", None) if request.user.is_authenticated else None

    for sp in products:
        nd = sp.normalized_data
        if not nd:
            skipped_count += 1
            continue

        name = nd.get("name", "").strip()
        if not name:
            skipped_count += 1
            continue

        try:
            # 1. Game (case insensitive matching)
            if game is None:
                # STANDALONE：按名稱找/建 Game
                game = Game.objects.filter(canonical_name__iexact=name).first()
                if not game:
                    game = Game.objects.create(canonical_name=name)
            else:
                # EXPANSION/VARIANT/BUNDLE：game 是 parent_game
                # 找/建以該名稱為主、parent_game 指向 parent 的 expansion Game
                parent_game = game
                game = Game.objects.filter(canonical_name__iexact=name, parent_game=parent_game).first()
                if not game:
                    game = Game.objects.create(
                        canonical_name=name,
                        kind=game_kind,
                        parent_game=parent_game,
                    )

            # 更新 Game 的 BGG 資訊（若為空且 normalized_data 有值）
            game_updated_fields = []

            if game.kind is None and game_kind:
                game.kind = game_kind
                game_updated_fields.append("kind")

            for field in ("min_players", "max_players", "min_playtime", "max_playtime"):
                if getattr(game, field) is None and nd.get(field) is not None:
                    setattr(game, field, nd[field])
                    game_updated_fields.append(field)

            if game.bgg_id is None and nd.get("bgg_id"):
                try:
                    game.bgg_id = int(nd.get("bgg_id"))
                    game_updated_fields.append("bgg_id")
                except (ValueError, TypeError):
                    pass

            if game.bgg_category is None and nd.get("categories"):
                categories = nd.get("categories")
                if isinstance(categories, list):
                    game.bgg_category = categories
                elif isinstance(categories, str):
                    game.bgg_category = [c.strip() for c in categories.split(",") if c.strip()]
                else:
                    game.bgg_category = [str(categories)]
                game_updated_fields.append("bgg_category")

            if game.bgg_mechanism is None and nd.get("mechanisms"):
                mechanisms = nd.get("mechanisms")
                if isinstance(mechanisms, list):
                    game.bgg_mechanism = mechanisms
                elif isinstance(mechanisms, str):
                    game.bgg_mechanism = [m.strip() for m in mechanisms.split(",") if m.strip()]
                else:
                    game.bgg_mechanism = [str(mechanisms)]
                game_updated_fields.append("bgg_mechanism")

            if game_updated_fields:
                game.save(update_fields=list(set(game_updated_fields)))

            # 2. Edition
            edition_defaults = {
                "summary": nd.get("summary", ""),
                "is_primary": is_primary,
            }
            if nd.get("age") is not None:
                edition_defaults["age"] = nd["age"]
            barcode_val = nd.get("barcode", "__MISSING__")
            if barcode_val not in ("__MISSING__", None, ""):
                edition_defaults["barcode"] = str(barcode_val).strip()
            if nd.get("msrp"):
                edition_defaults["msrp"] = nd["msrp"]

            # currency：表單選擇優先，其次看 normalized_data，最後 fallback USD
            cur_obj = None
            if currency is not None:
                cur_obj = currency
            else:
                currency_code = nd.get("msrp_currency")
                if currency_code:
                    cur_obj = Currency.objects.filter(code=currency_code).first()
                if cur_obj is None:
                    cur_obj = Currency.objects.filter(code="USD").first()
            if cur_obj:
                edition_defaults["msrp_currency"] = cur_obj

            # region：表單選擇優先，其次看 normalized_data.region_code / region
            region_obj = None
            if region is not None:
                region_obj = region
            else:
                region_code = nd.get("region_code") or nd.get("region")
                if region_code:
                    region_obj = Region.objects.filter(code=region_code).first()
            if region_obj:
                edition_defaults["region"] = region_obj

            # 使用 alternate_name 作為 edition name，若無則沿用 name
            edition_name = nd.get("alternate_name") or name

            edition, ed_created = Edition.objects.get_or_create(
                game=game,
                language=language,
                name=edition_name,
                defaults=edition_defaults,
            )

            # Note: 若 DB 已有 barcode 值，即使匯入為空值也保留原值（leave as is）

            # 設定 packaging_languages：表單選擇優先，其次看 normalized_data
            if packaging_languages is not None and packaging_languages.exists():
                edition.packaging_languages.set(packaging_languages)
            else:
                packaging_langs = nd.get("packaging_languages") or nd.get("packaging_language_codes")
                if packaging_langs:
                    # 允許字串或 list
                    if isinstance(packaging_langs, str):
                        codes = [c.strip() for c in packaging_langs.split(",") if c.strip()]
                    else:
                        codes = [str(c).strip() for c in packaging_langs if str(c).strip()]
                    tribes = []
                    for code in codes:
                        tribe = Tribe.objects.filter(language=code).first() or Tribe.objects.filter(name=code).first()
                        if tribe:
                            tribes.append(tribe)
                    if tribes:
                        edition.packaging_languages.add(*tribes)

            # 下載 thumbnail
            # thumbnail_choice="db"  → 保留 DB 現有圖；"scraped" → 強制換成 scraped 圖；
            # None（無 radio，代表新 edition）→ 只在沒有圖時下載
            if thumbnail_choice == "db":
                pass
            elif nd.get("thumbnail_url"):
                if thumbnail_choice == "scraped" or not edition.thumbnail:
                    fname, fobj = _download_file(nd["thumbnail_url"])
                    if fobj:
                        if edition.thumbnail:
                            edition.thumbnail.delete(save=False)
                        edition.thumbnail.save(fname, fobj, save=True)

            # 4. EditionRole – publisher
            if publisher_entity:
                EditionRole.objects.get_or_create(
                    edition=edition,
                    entity=publisher_entity,
                    role="publisher",
                )

            # 4b. Designer / Artist roles（支持多種格式：字串、list 或 JSON）
            for role_key in ("designer", "artist"):
                raw_data = nd.get(role_key)
                if not raw_data:
                    continue
                
                # 支援多種格式的輸入
                person_names = []
                if isinstance(raw_data, str):
                    # 字串格式：用分號或逗號分割
                    person_names = [n.strip() for n in raw_data.replace(",", ";").split(";") if n.strip()]
                elif isinstance(raw_data, list):
                    # List 格式
                    person_names = [str(n).strip() for n in raw_data if str(n).strip()]
                else:
                    # 其他格式轉字串後處理
                    person_names = [str(raw_data).strip()]
                
                for person_name in person_names:
                    if not person_name:
                        continue
                    # Truncate to 200 characters to match Entity.name max_length
                    person_name = person_name[:200]
                    person_entity, _ = Entity.objects.get_or_create(
                        name=person_name,
                        defaults={"entity_type": "individual"},
                    )
                    EditionRole.objects.get_or_create(
                        edition=edition,
                        entity=person_entity,
                        role=role_key,
                    )

            # 5. Rulebook — 合併 normalized_data["rulebooks"] 與 raw_data["rulebook_urls"]
            rulebooks_list = _merge_rulebooks(nd, sp.raw_data)
            if rulebooks_list:
                # 新格式：rulebooks 是一個 list of dicts，每個都有 language 和 url
                for rb_info in rulebooks_list:
                    rb_url = rb_info.get("url")
                    rb_lang_code = rb_info.get("language")
                    
                    if not rb_url:
                        continue
                    
                    # 根據語言代碼查找對應的 Tribe
                    rb_tribe = _get_tribe_by_lang_code(rb_lang_code)
                    if not rb_tribe:
                        # 若找不到 Tribe，使用預設的 language
                        print(f"[IMPORT] No tribe found for language code '{rb_lang_code}', using default language")
                        rb_tribe = language
                    
                    # 檢查是否已經存在相同 source_url 的 rulebook
                    existing_rulebook = Rulebook.objects.filter(
                        edition=edition,
                        source_url=rb_url
                    ).first()
                    
                    if existing_rulebook:
                        print(f"[IMPORT] Rulebook already exists for {rb_url}, skipping")
                        continue
                    
                    # 為新的 rulebook 創建對象
                    # 如果已經有相同 language 的 rulebook，會先檢查
                    rulebook, rb_created = Rulebook.objects.get_or_create(
                        edition=edition,
                        language=rb_tribe,
                        source_url=rb_url,  # 作為額外的唯一性檢查
                        defaults={
                            "title": f"{name} Rulebook ({rb_lang_code})" if rb_lang_code else f"{name} Rulebook",
                        },
                    )
                    
                    print(f"[IMPORT] Rulebook {'created' if rb_created else 'retrieved'}: {rb_url} ({rb_tribe.name})")
                    
                    # 下載並保存文件
                    if rb_created or not rulebook.file:
                        fname, fobj = _download_file(rb_url)
                        if fobj:
                            rulebook.file.save(fname, fobj, save=True)
                            print(f"[IMPORT] File saved for {rb_url}")
                        else:
                            print(f"[IMPORT] Failed to download {rb_url}")
            
            # 後備：處理舊的 rulebook_url 格式（向後相容）
            elif nd.get("rulebook_url"):
                rulebook, rb_created = Rulebook.objects.get_or_create(
                    edition=edition,
                    language=language,
                    defaults={
                        "title": f"{name} Rulebook",
                        "source_url": nd["rulebook_url"],
                    },
                )
                if rb_created or not rulebook.file:
                    fname, fobj = _download_file(nd["rulebook_url"])
                    if fobj:
                        rulebook.file.save(fname, fobj, save=True)
                    if not rulebook.source_url:
                        rulebook.source_url = nd["rulebook_url"]
                        rulebook.save(update_fields=["source_url"])

            # 6. 更新 ScrapedProduct
            sp.status = ScrapedProduct.Status.IMPORTED
            sp.imported_edition = edition
            sp.reviewed_at = timezone.now()
            sp.reviewed_by = reviewer
            sp.save(update_fields=["status", "imported_edition", "reviewed_at", "reviewed_by", "updated_at"])

            created_count += 1

            # 7. GameTitle（依語言建立主標題）
            from .models import GameTitle
            if language:
                GameTitle.objects.get_or_create(
                    game=game,
                    language=language,
                    title=name,
                    defaults={"is_primary": True},
                )

        except Exception as exc:
            error_msgs.append(f"{name}: {exc}")

    return created_count, skipped_count, error_msgs


def _do_import_variant(
    request,
    products,
    language,
    publisher_entity,
    is_primary,
    game_title_language=None,
    currency=None,
    region=None,
    packaging_languages=None,
):
    """
    匯入 Variant：不建立新 Game，而是在現有 Game 上新增 Edition 和 GameTitle。
    - 以 product.name 找現有 Game
    - 新增 Edition（name = alternate_name or name）到該 Game
    - 新增 GameTitle（title = edition_name, language = game_title_language）到該 Game
    - Thumbnail 直接用 scraped 圖，不作選擇
    """
    from django.utils import timezone
    from commerce.models import Currency
    from translation.models import Region

    created_count = 0
    skipped_count = 0
    error_msgs = []

    reviewer = getattr(request.user, "member", None) if request.user.is_authenticated else None

    for sp in products:
        nd = sp.normalized_data
        if not nd:
            skipped_count += 1
            continue

        name = nd.get("name", "").strip()
        if not name:
            skipped_count += 1
            continue

        try:
            # 1. 找現有 Game
            game = Game.objects.filter(canonical_name__iexact=name).first()
            if not game:
                error_msgs.append(f"{name}: 找不到對應的 Game，請先確認 DB 中有此 game。")
                continue

            # 2. Edition（新增至現有 Game）
            edition_name = nd.get("alternate_name") or name
            edition_defaults = {
                "summary": nd.get("summary", ""),
                "is_primary": is_primary,
            }
            if nd.get("age") is not None:
                edition_defaults["age"] = nd["age"]

            cur_obj = None
            if currency is not None:
                cur_obj = currency
            else:
                currency_code = nd.get("msrp_currency")
                if currency_code:
                    cur_obj = Currency.objects.filter(code=currency_code).first()
                if cur_obj is None:
                    cur_obj = Currency.objects.filter(code="USD").first()
            if cur_obj:
                edition_defaults["msrp_currency"] = cur_obj

            if nd.get("msrp"):
                edition_defaults["msrp"] = nd["msrp"]

            region_obj = None
            if region is not None:
                region_obj = region
            else:
                region_code = nd.get("region_code") or nd.get("region")
                if region_code:
                    region_obj = Region.objects.filter(code=region_code).first()
            if region_obj:
                edition_defaults["region"] = region_obj

            edition, _ = Edition.objects.get_or_create(
                game=game,
                language=language,
                name=edition_name,
                defaults=edition_defaults,
            )

            # packaging_languages
            if packaging_languages is not None and packaging_languages.exists():
                edition.packaging_languages.set(packaging_languages)

            # 3. Thumbnail（直接用 scraped，不作選擇）
            if nd.get("thumbnail_url") and not edition.thumbnail:
                fname, fobj = _download_file(nd["thumbnail_url"])
                if fobj:
                    edition.thumbnail.save(fname, fobj, save=True)

            # 4. EditionRole – publisher / designer / artist
            if publisher_entity:
                EditionRole.objects.get_or_create(edition=edition, entity=publisher_entity, role="publisher")

            for role_key in ("designer", "artist"):
                raw_val = nd.get(role_key)
                if not raw_val:
                    continue
                if isinstance(raw_val, list):
                    names_list = raw_val
                elif isinstance(raw_val, str):
                    import re as _re
                    names_list = [n.strip() for n in _re.split(r"[,;]", raw_val) if n.strip()]
                else:
                    names_list = [str(raw_val).strip()]
                for person_name in names_list:
                    if not person_name:
                        continue
                    entity, _ = Entity.objects.get_or_create(
                        name=person_name,
                        defaults={"entity_type": "individual"},
                    )
                    EditionRole.objects.get_or_create(edition=edition, entity=entity, role=role_key)

            # 5. GameTitle（新增至現有 Game）
            from .models import GameTitle
            GameTitle.objects.get_or_create(
                game=game,
                title=edition_name,
                language=game_title_language,
                defaults={"is_primary": False},
            )

            # 6. 更新 ScrapedProduct
            sp.status = ScrapedProduct.Status.IMPORTED
            sp.imported_edition = edition
            sp.reviewed_at = timezone.now()
            sp.reviewed_by = reviewer
            sp.save(update_fields=["status", "imported_edition", "reviewed_at", "reviewed_by", "updated_at"])

            created_count += 1

        except Exception as exc:
            error_msgs.append(f"{name}: {exc}")

    return created_count, skipped_count, error_msgs


def _do_import_bgg(request, products, thumbnail_choices):
    """
    匯入 BGG Data：
    - 找現有 Game，只補空白欄位（bgg_id / categories / mechanisms / players / playtime）
    - 若 game 只有一筆 edition，依 thumbnail_choices 決定是否替換縮圖
    - 絕不建立新 Edition
    thumbnail_choices: dict[str(sp.id)] → "db" | "scraped" | None
    """
    from django.utils import timezone

    created_count = 0
    skipped_count = 0
    error_msgs = []

    reviewer = getattr(request.user, "member", None) if request.user.is_authenticated else None

    for sp in products:
        nd = sp.normalized_data
        if not nd:
            skipped_count += 1
            continue

        name = nd.get("name", "").strip()
        if not name:
            skipped_count += 1
            continue

        try:
            game = Game.objects.filter(canonical_name__iexact=name).first()
            if not game:
                error_msgs.append(f"{name}: 找不到對應的 Game，請先確認 DB 中有此 game。")
                continue

            # 補空白 Game 欄位
            game_updated_fields = []
            if game.bgg_id is None and nd.get("bgg_id"):
                try:
                    game.bgg_id = int(nd["bgg_id"])
                    game_updated_fields.append("bgg_id")
                except (ValueError, TypeError):
                    pass
            if game.bgg_category is None and nd.get("categories"):
                cats = nd["categories"]
                game.bgg_category = cats if isinstance(cats, list) else [c.strip() for c in cats.split(",") if c.strip()]
                game_updated_fields.append("bgg_category")
            if game.bgg_mechanism is None and nd.get("mechanisms"):
                mechs = nd["mechanisms"]
                game.bgg_mechanism = mechs if isinstance(mechs, list) else [m.strip() for m in mechs.split(",") if m.strip()]
                game_updated_fields.append("bgg_mechanism")
            for field in ("min_players", "max_players", "min_playtime", "max_playtime"):
                if getattr(game, field) is None and nd.get(field) is not None:
                    setattr(game, field, nd[field])
                    game_updated_fields.append(field)
            if game_updated_fields:
                game.save(update_fields=list(set(game_updated_fields)))

            # 處理 thumbnail（僅當 game 只有 1 筆 edition）
            eds = list(game.editions.all()[:2])
            if len(eds) == 1:
                edition = eds[0]
                choice = thumbnail_choices.get(str(sp.id))
                if choice == "scraped" and nd.get("thumbnail_url"):
                    fname, fobj = _download_file(nd["thumbnail_url"])
                    if fobj:
                        if edition.thumbnail:
                            edition.thumbnail.delete(save=False)
                        edition.thumbnail.save(fname, fobj, save=True)
                # choice == "db" or None → 保留現有縮圖，不動

                # 補空白 age
                if edition.age is None and nd.get("age") is not None:
                    edition.age = nd["age"]
                    edition.save(update_fields=["age", "updated_at"])

            # 更新 ScrapedProduct 狀態
            sp.status = ScrapedProduct.Status.IMPORTED
            sp.reviewed_at = timezone.now()
            sp.reviewed_by = reviewer
            sp.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])

            created_count += 1

        except Exception as exc:
            error_msgs.append(f"{name}: {exc}")

    return created_count, skipped_count, error_msgs


# ---------------------------------------------------------------------------
# ScrapedProduct Admin
# ---------------------------------------------------------------------------

class CompanyEntityFilter(admin.SimpleListFilter):
    title = 'Entity'
    parameter_name = 'entity'

    def lookups(self, request, model_admin):
        from .models import Entity
        entities = Entity.objects.filter(entity_type='company').order_by('name')
        return [(e.id, e.name) for e in entities]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(scrapelog__publisher_id=self.value())
        return queryset


class HasRankFilter(admin.SimpleListFilter):
    title = '是否有排名'
    parameter_name = 'has_rank'

    def lookups(self, request, model_admin):
        return [
            ('yes', '有排名 (1+)'),
            ('no', '無排名 (None/0)'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(rank__gt=0)
        if self.value() == 'no':
            return queryset.filter(models.Q(rank__isnull=True) | models.Q(rank=0))
        return queryset


class HasRulebookFilter(admin.SimpleListFilter):
    title = 'Rulebook'
    parameter_name = 'has_rulebook'

    def lookups(self, request, model_admin):
        return [('yes', '有 Rulebook'), ('no', '無 Rulebook')]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.exclude(normalized_data__rulebook_url__isnull=True).exclude(normalized_data__rulebook_url='')
        if self.value() == 'no':
            return queryset.filter(
                models.Q(normalized_data__rulebook_url__isnull=True) |
                models.Q(normalized_data__rulebook_url='')
            )
        return queryset


@admin.register(ScrapedProduct)
class ScrapedProductAdmin(admin.ModelAdmin):
    list_filter = (
        "status", CompanyEntityFilter, HasRankFilter, HasRulebookFilter,
    )
    list_display = (
        # "id",
        "product_name_display", "db_conflict_display", "scrapelog_link", "players_display", "status_display",
        "dimension_total", "has_thumbnail", "has_rulebook",
        # "normalized_data",
        "imported_edition_link",
        "rank_display", "family_rank_display", "party_rank_display", "reviewed_at", #"created_at",
    )
    list_per_page = 20

    search_fields = (
        "imported_edition__name",
        "imported_edition__barcode",
        "imported_edition__game__canonical_name",
    )
    raw_id_fields = ("scrapelog", "reviewed_by")

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term:
            # Search in normalized_data JSON field's name property
            queryset |= self.model.objects.filter(
                normalized_data__name__icontains=search_term
            )
        return queryset, use_distinct
    autocomplete_fields = ("imported_edition",)
    
    @admin.display(description="Rank", ordering="rank")
    def rank_display(self, obj):
        if obj.rank is None: return "—"
        if obj.rank == 0: return "(unranked)"
        return obj.rank

    @admin.display(description="Family Rank", ordering="family_rank")
    def family_rank_display(self, obj):
        if obj.family_rank is None: return "—"
        if obj.family_rank == 0: return "(unranked)"
        return obj.family_rank

    @admin.display(description="Party Rank", ordering="party_rank")
    def party_rank_display(self, obj):
        if obj.party_rank is None: return "—"
        if obj.party_rank == 0: return "(unranked)"
        return obj.party_rank

    readonly_fields = ("created_at", "updated_at", "normalized_data_pretty")
    actions = [
        "action_import_new_game", "action_import_variant", "action_import_bgg_data",
        "update_existing_records", "set_status_rejected", "set_status_expansion",
    ]
    # exclude = ("status",)  # Exclude status field from all forms to prevent access to removed choices
    
    fieldsets = (
        (None, {
            "fields": (
                "scrapelog", "imported_edition", "reviewed_by", "reviewed_at",
                "raw_data", "normalized_data_pretty",
            )
        }),
        ("Status", {
            "fields": ("status",),
        }),
    )

    def get_queryset(self, request):
        from django.db.models import Exists, OuterRef
        from django.db.models.expressions import RawSQL
        from django.db.models.functions import Lower
        # 先把 JSON 裡的 name 萃取成小寫字串，再與 Game.canonical_name 小寫比對
        qs = super().get_queryset(request).annotate(
            nd_name_lower=Lower(RawSQL("normalized_data->>'name'", []))
        )
        game_exists_sq = Game.objects.annotate(
            lower_canonical=Lower("canonical_name")
        ).filter(lower_canonical=OuterRef("nd_name_lower"))
        return qs.annotate(db_conflict=Exists(game_exists_sq))

    def get_form(self, request, obj=None, change=False, **kwargs):
        reviewer = getattr(request.user, "member", None) if getattr(request, "user", None) and request.user.is_authenticated else None
        base_form = super().get_form(request, obj=obj, change=change, **kwargs)

        if not reviewer or "reviewed_by" not in base_form.base_fields:
            return base_form

        # raw_id_fields + change form 時，若 instance 欄位是 None，Django 不一定會顯示 field.initial
        # 這裡用 wrapper form 強制在 __init__ 時補上 initial（僅當 instance.reviewed_by 為空）
        class WrappedForm(base_form):
            def __init__(self2, *args, **kwargs2):
                super().__init__(*args, **kwargs2)
                instance = getattr(self2, "instance", None)
                if instance is not None and getattr(instance, "reviewed_by_id", None) is None:
                    self2.fields["reviewed_by"].initial = reviewer.pk
                    # 同步 form.initial，確保 raw_id widget 也能吃到值
                    self2.initial["reviewed_by"] = reviewer.pk

        return WrappedForm

    # ── Display helpers ────────────────────────────────────────────────────

    @admin.display(description="ScrapeLog")
    def scrapelog_link(self, obj):
        url = reverse("admin:game_scrapelog_change", args=[obj.scrapelog.id])
        return format_html('<a href="{}">{}</a>', url, obj.scrapelog.publisher.name)

    @admin.display(description="Imported Edition")
    def imported_edition_link(self, obj):
        if not obj.imported_edition_id:
            return "-"
        url = reverse("admin:game_edition_change", args=[obj.imported_edition_id])
        return format_html('<a href="{}">{}</a>', url, str(obj.imported_edition))

    imported_edition_link.admin_order_field = "imported_edition__name"

    @admin.display(description="名稱")
    def product_name_display(self, obj):
        nd = obj.normalized_data or {}
        name = nd.get("name", "")
        # url = nd.get("url", "")
        # if url:
        #     return format_html('<a href="{}" target="_blank">{}</a>', url, name or "(no name)")
        return name or "(no name)"

    @admin.display(description="DB", ordering="db_conflict")
    def db_conflict_display(self, obj):
        if getattr(obj, "db_conflict", False):
            return "⚠️"
        return ""

    @admin.display(description="Thumbnail", boolean=True)
    def has_thumbnail(self, obj):
        return bool((obj.normalized_data or {}).get("thumbnail_url"))

    @admin.display(description="Rulebook", boolean=True)
    def has_rulebook(self, obj):
        return bool((obj.normalized_data or {}).get("rulebook_url"))

    @admin.display(description="Status")
    def status_display(self, obj):
        status_colors = {
            'pending': '#FFA500',  # Orange
            'rejected': '#FF4444',  # Red  
            'imported': '#44BB44',  # Green
        }
        status_emojis = {
            'pending': '⏳',
            'rejected': '❌',
            'imported': '✅',
        }
        color = status_colors.get(obj.status, '#666666')
        emoji = status_emojis.get(obj.status, '❓')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color, emoji, obj.get_status_display()
        )

    @admin.display(description="Players")
    def players_display(self, obj):
        nd = obj.normalized_data or {}
        min_players = nd.get("min_players")
        max_players = nd.get("max_players")
        if min_players is not None and max_players is not None:
            return f"{min_players}-{max_players}"
        elif max_players is not None:
            return max_players
        return "-"

    @admin.display(description="Dimension Total")
    def dimension_total(self, obj):
        import json
        import os
        
        nd = obj.normalized_data or {}
        # Use correct key names: mechanisms and categories
        bgg_mechanics = nd.get("mechanisms", [])
        bgg_categories = nd.get("categories", [])
        
        if not bgg_mechanics and not bgg_categories:
            return "-"
        
        # Load BGG platvm JSON
        json_path = os.path.join(os.path.dirname(__file__), 'config', 'bgg_platvm.json')
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                bgg_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return "-"
        
        # Get mechanics and categories sections from JSON
        mechanics_data = bgg_data.get("mechanics", {})
        categories_data = bgg_data.get("categories", {})
        
        # Initialize result arrays for 6 skills
        result_arrays = {
            'adaptability': [0, 0, 0, 0, 0],
            'collaboration': [0, 0, 0, 0, 0], 
            'communication': [0, 0, 0, 0, 0],
            'creativity': [0, 0, 0, 0, 0],
            'critical_thinking': [0, 0, 0, 0, 0],
            'problem_solving': [0, 0, 0, 0, 0]
        }
        
        # Process mechanics (look up in mechanics section)
        for mechanic in bgg_mechanics:
            mechanic_entry = mechanics_data.get(mechanic)
            if mechanic_entry:
                for skill in result_arrays.keys():
                    if skill in mechanic_entry:
                        current_array = mechanic_entry[skill]
                        # OR operation: result[i] = max(result[i], current_array[i])
                        for i in range(5):
                            result_arrays[skill][i] = max(result_arrays[skill][i], current_array[i])
        
        # Process categories (look up in categories section)
        for category in bgg_categories:
            category_entry = categories_data.get(category)
            if category_entry:
                for skill in result_arrays.keys():
                    if skill in category_entry:
                        current_array = category_entry[skill]
                        # OR operation: result[i] = max(result[i], current_array[i])
                        for i in range(5):
                            result_arrays[skill][i] = max(result_arrays[skill][i], current_array[i])
        
        # Calculate total sum of all 6 skills
        total = 0
        for skill_array in result_arrays.values():
            total += sum(skill_array)
        
        return total

    @admin.display(description="Normalized Data")
    def normalized_data_pretty(self, obj):
        try:
            nd = dict(obj.normalized_data or {})
            # 合併 raw_data["rulebook_urls"]，以利顯示完整 PDF 清單
            nd["rulebooks"] = _merge_rulebooks(nd, obj.raw_data)
            if not nd:
                return "-"

            # 定義欄位顯示名稱對照
            field_labels = {
                'name': '名稱',
                'url': '網址',
                'alternate_name': '別名',
                'summary': '簡介',
                'min_players': '最少玩家',
                'max_players': '最多玩家',
                'min_playtime': '最短時間',
                'max_playtime': '最長時間',
                'age': '適齡',
                'designer': '設計師',
                'artist': '美術',
                'msrp': '建議售價',
                'rulebook_url': '規則書網址 (舊格式)',
                'rulebooks': '規則書 (多語言)',
                'thumbnail_url': '縮圖網址',
                'price': '價格',
                'currency': '貨幣',
                'barcode': '條碼',
                'image_url': '圖片網址',
                'language': '語言',
                'publisher_name': '發行商',
                'mechanisms': '機制',
                'categories': '分類',
            }

            # 將列表欄位格式化為逗號分隔的字串
            def format_value(key, value):
                if key == 'rulebooks' and isinstance(value, list):
                    if not value:
                        return '(無)'
                    items = []
                    for rb in value:
                        if isinstance(rb, dict):
                            lang = rb.get('language') or '?'
                            url = rb.get('url') or ''
                            items.append(f"[{lang}] {url}")
                        else:
                            items.append(str(rb))
                    return f"({len(value)} 本)<br>&nbsp;&nbsp;" + "<br>&nbsp;&nbsp;".join(items)
                if isinstance(value, list):
                    return ', '.join(str(v) for v in value)
                return str(value)

            rows = []
            for key, value in nd.items():
                if value is not None and value != '':
                    label = field_labels.get(key, key)
                    formatted_value = format_value(key, value)
                    # 對於較長的值（如網址），加上換行和縮排
                    if isinstance(value, str) and len(formatted_value) > 50:
                        rows.append(f"<strong>{label}:</strong><br>&nbsp;&nbsp;{formatted_value}")
                    elif key == 'rulebooks':
                        rows.append(f"<strong>{label}:</strong> {formatted_value}")
                    else:
                        rows.append(f"<strong>{label}:</strong> {formatted_value}")

            return format_html(
                '<div style="background:var(--body-bg,#f5f5f5);color:var(--body-fg,#333);padding:10px;overflow-x:auto;max-width:800px;line-height:1.8;border:1px solid var(--border-color,#ccc);border-radius:4px;">{}</div>',
                format_html('<br>'.join(rows))
            )
        except Exception as e:
            return f"Error: {str(e)}"

    # ── Custom URLs ────────────────────────────────────────────────────────

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("import-new-game/", self.admin_site.admin_view(self.import_new_game_view),
                 name="game_scrapedproduct_import_new_game"),
            path("import-variant/",  self.admin_site.admin_view(self.import_variant_view),
                 name="game_scrapedproduct_import_variant"),
            path("import-bgg/",      self.admin_site.admin_view(self.import_bgg_view),
                 name="game_scrapedproduct_import_bgg"),
        ]
        return custom_urls + urls

    # ── Actions ────────────────────────────────────────────────────────────

    def _check_game_exists_map(self):
        """回傳 {canonical_name.lower(): True} 供 action 驗證用"""
        return {g.canonical_name.lower() for g in Game.objects.only("canonical_name") if g.canonical_name}

    @admin.action(description="📥 匯入新 Game")
    def action_import_new_game(self, request, queryset):
        selected_ids = list(queryset.values_list("id", flat=True))
        if not selected_ids:
            self.message_user(request, "請先勾選資料。", level=messages.WARNING)
            return
        game_names = self._check_game_exists_map()
        conflicts = [
            (sp.normalized_data or {}).get("name", "")
            for sp in queryset
            if (sp.normalized_data or {}).get("name", "").lower() in game_names
        ]
        if conflicts:
            self.message_user(
                request,
                f"❌ 以下項目在 DB 中已有同名 Game，請改用「匯入 Variant」或「匯入 BGG Data」：{', '.join(conflicts)}",
                level=messages.ERROR,
            )
            return
        request.session["scraped_import_new_game_ids"] = [str(i) for i in selected_ids]
        return redirect(reverse("admin:game_scrapedproduct_import_new_game"))

    @admin.action(description="📥 匯入 Variant")
    def action_import_variant(self, request, queryset):
        selected_ids = list(queryset.values_list("id", flat=True))
        if not selected_ids:
            self.message_user(request, "請先勾選資料。", level=messages.WARNING)
            return
        game_names = self._check_game_exists_map()
        missing = [
            (sp.normalized_data or {}).get("name", "")
            for sp in queryset
            if (sp.normalized_data or {}).get("name", "").lower() not in game_names
        ]
        if missing:
            self.message_user(
                request,
                f"❌ 以下項目在 DB 中找不到同名 Game（無法作為 parent），請先匯入新 Game：{', '.join(missing)}",
                level=messages.ERROR,
            )
            return
        request.session["scraped_import_variant_ids"] = [str(i) for i in selected_ids]
        return redirect(reverse("admin:game_scrapedproduct_import_variant"))

    @admin.action(description="📥 匯入 BGG Data")
    def action_import_bgg_data(self, request, queryset):
        selected_ids = list(queryset.values_list("id", flat=True))
        if not selected_ids:
            self.message_user(request, "請先勾選資料。", level=messages.WARNING)
            return
        game_names = self._check_game_exists_map()
        missing = [
            (sp.normalized_data or {}).get("name", "")
            for sp in queryset
            if (sp.normalized_data or {}).get("name", "").lower() not in game_names
        ]
        if missing:
            self.message_user(
                request,
                f"❌ 以下項目在 DB 中找不到同名 Game，BGG Data 匯入需要 game 已存在：{', '.join(missing)}",
                level=messages.ERROR,
            )
            return
        request.session["scraped_import_bgg_ids"] = [str(i) for i in selected_ids]
        return redirect(reverse("admin:game_scrapedproduct_import_bgg"))

    @admin.action(description="🧩 設定為擴充版 (Expansion)")
    def set_status_expansion(self, request, queryset):
        from django.utils import timezone

        updated = queryset.update(
            status=ScrapedProduct.Status.EXPANSION,
            reviewed_at=timezone.now()
        )

        self.message_user(
            request,
            f"✅ 已將 {updated} 筆 ScrapedProduct 設定為擴充版狀態",
            level=messages.SUCCESS
        )

    @admin.action(description="🗑️ 設定為已拒絕 (Rejected)")
    def set_status_rejected(self, request, queryset):
        from django.utils import timezone
        
        updated = queryset.update(
            status=ScrapedProduct.Status.REJECTED,
            reviewed_at=timezone.now()
        )
        
        self.message_user(
            request,
            f"✅ 已將 {updated} 筆 ScrapedProduct 設定為已拒絕狀態",
            level=messages.SUCCESS
        )

    @admin.action(description="🔄 強行更新(Game/Package/Edition)[全覆蓋,慎用]")
    def update_existing_records(self, request, queryset):
        """更新已存在對應 Edition 的 ScrapedProduct 資料"""
        from django.utils import timezone
        
        # 只處理有 imported_edition 的記錄
        products_with_edition = queryset.filter(imported_edition__isnull=False)
        skipped_count = queryset.count() - products_with_edition.count()
        
        if not products_with_edition.exists():
            self.message_user(
                request,
                f"⚠️ 沒有找到已對應 Edition 的記錄，跳過 {skipped_count} 筆",
                level=messages.WARNING
            )
            return
        
        updated_count, error_count = _do_update_existing(request, products_with_edition)
        
        # 顯示結果訊息
        if updated_count > 0:
            self.message_user(
                request,
                f"✅ 成功更新 {updated_count} 筆記錄",
                level=messages.SUCCESS
            )
        if error_count > 0:
            self.message_user(
                request,
                f"❌ 更新失敗 {error_count} 筆記錄",
                level=messages.ERROR
            )
        if skipped_count > 0:
            self.message_user(
                request,
                f"⏭️ 跳過 {skipped_count} 筆無對應 Edition 的記錄",
                level=messages.WARNING
            )

    # ── Shared helpers ─────────────────────────────────────────────────────

    class _NdProxy:
        """Let template access normalized_data dict keys as attributes."""
        def __init__(self, d):
            self._d = d or {}
        def __getattr__(self, key):
            value = self._d.get(key)
            if key in ('categories', 'mechanisms'):
                if isinstance(value, list):
                    return ", ".join(str(v) for v in value)
            return value

    def _build_preview_products(self, request, products_qs, *, include_existing_edition=False):
        """Build the preview_products list used by all three confirm views."""
        games = list(Game.objects.all().order_by("canonical_name"))
        game_names_lower = [g.canonical_name.lower() for g in games if g.canonical_name]
        game_name_map = {g.canonical_name.lower(): g for g in games if g.canonical_name}

        preview_products = []
        for sp in products_qs:
            product_name = (sp.normalized_data or {}).get("name", "").lower()
            game_exists = bool(product_name and product_name in game_names_lower)

            existing_edition = None
            if include_existing_edition and game_exists:
                matched_game = game_name_map.get(product_name)
                if matched_game:
                    eds = list(matched_game.editions.all()[:2])
                    if len(eds) == 1:
                        existing_edition = eds[0]

            nd_merged = dict(sp.normalized_data or {})
            nd_merged["rulebooks"] = _merge_rulebooks(nd_merged, sp.raw_data)
            preview_products.append({
                "obj": sp,
                "nd": self._NdProxy(nd_merged),
                "game_exists": game_exists,
                "existing_edition": existing_edition,
            })
        return preview_products, games

    def _update_normalized_data(self, request, products_qs, *, include_barcode=True, include_alternate_name=True):
        """Write per-row form inputs back into ScrapedProduct.normalized_data."""
        for sp in products_qs:
            nd = sp.normalized_data or {}
            changed = False

            name_val = (request.POST.get(f"name_{sp.id}") or "").strip()
            if name_val:
                nd["name"] = name_val
                changed = True

            if include_alternate_name and f"alternate_name_{sp.id}" in request.POST:
                nd["alternate_name"] = (request.POST.get(f"alternate_name_{sp.id}") or "").strip() or None
                changed = True

            if include_barcode and f"barcode_{sp.id}" in request.POST:
                nd["barcode"] = (request.POST.get(f"barcode_{sp.id}") or "").strip() or None
                changed = True

            for key in ("designer", "artist"):
                field_key = f"{key}_{sp.id}"
                if field_key in request.POST:
                    nd[key] = request.POST.get(field_key, "").strip() or None
                    changed = True

            bgg_id_val = (request.POST.get(f"bgg_id_{sp.id}") or "").strip()
            if bgg_id_val:
                try:
                    nd["bgg_id"] = int(bgg_id_val)
                    changed = True
                except ValueError:
                    pass

            for key in ("categories", "mechanisms"):
                val = (request.POST.get(f"{key}_{sp.id}") or "").strip()
                if val:
                    try:
                        if val.startswith("["):
                            nd[key] = json.loads(val)
                        else:
                            nd[key] = [v.strip() for v in val.split(",") if v.strip()]
                    except (ValueError, TypeError):
                        nd[key] = val
                    changed = True

            if changed:
                sp.normalized_data = nd
                sp.save(update_fields=["normalized_data", "updated_at"])

    def _flash_results(self, request, created, skipped, errors):
        if created:
            self.message_user(request, f"✅ 成功匯入 {created} 筆資料。", level=messages.SUCCESS)
        if skipped:
            self.message_user(request, f"⏭️ 跳過 {skipped} 筆（缺少名稱或 normalized_data）。", level=messages.WARNING)
        for err in errors:
            self.message_user(request, f"❌ {err}", level=messages.ERROR)

    def _reviewer_display(self, request):
        return (
            getattr(getattr(request.user, "member", None), "id", None)
            or getattr(request.user, "username", str(request.user))
        )

    # ── Confirm views ──────────────────────────────────────────────────────

    def import_new_game_view(self, request):
        session_key = "scraped_import_new_game_ids"
        product_ids = request.POST.getlist("product_ids") if request.method == "POST" else request.session.get(session_key, [])
        products_qs = ScrapedProduct.objects.filter(id__in=product_ids)
        if not products_qs.exists():
            self.message_user(request, "找不到所選的 ScrapedProduct，請重試。", level=messages.WARNING)
            return redirect(reverse("admin:game_scrapedproduct_changelist"))

        preview_products, games = self._build_preview_products(request, products_qs, include_existing_edition=False)
        game_kind_choices = list(Game.Kind.choices)

        if request.method == "POST":
            form = ScrapedImportForm(request.POST)
            if form.is_valid():
                language = form.cleaned_data["language"]
                publisher_entity = form.cleaned_data["publisher_entity"]
                is_primary = form.cleaned_data["is_primary"]
                currency = form.cleaned_data.get("currency")
                region = form.cleaned_data.get("region")
                packaging_languages = form.cleaned_data.get("packaging_languages")

                self._update_normalized_data(request, products_qs, include_barcode=True, include_alternate_name=True)

                game_by_id = {str(g.id): g for g in games}
                created, skipped, errors = 0, 0, []
                for sp in products_qs:
                    kind = (request.POST.get(f"game_kind_{sp.id}") or "").strip() or Game.Kind.STANDALONE
                    game_id = (request.POST.get(f"game_{sp.id}") or "").strip()
                    selected_game = game_by_id.get(game_id) if game_id else None
                    if kind != Game.Kind.STANDALONE and not selected_game:
                        errors.append(f"{(sp.normalized_data or {}).get('name','(no name)')}: {kind} 需要指定 Parent Game")
                        continue
                    c, s, e = _do_import(
                        request, [sp], language, publisher_entity, kind, is_primary,
                        game=selected_game, currency=currency, region=region,
                        packaging_languages=packaging_languages, thumbnail_choice=None,
                    )
                    created += c; skipped += s; errors.extend(e)

                request.session.pop(session_key, None)
                self._flash_results(request, created, skipped, errors)
                return redirect(reverse("admin:game_scrapedproduct_changelist"))
        else:
            form = ScrapedImportForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "匯入新 Game",
            "form": form,
            "products": preview_products,
            "product_ids": product_ids,
            "games": games,
            "game_kind_choices": game_kind_choices,
            "reviewer_display": self._reviewer_display(request),
        }
        return render(request, "admin/game/scraped_import_new_game.html", context)

    def import_variant_view(self, request):
        session_key = "scraped_import_variant_ids"
        product_ids = request.POST.getlist("product_ids") if request.method == "POST" else request.session.get(session_key, [])
        products_qs = ScrapedProduct.objects.filter(id__in=product_ids)
        if not products_qs.exists():
            self.message_user(request, "找不到所選的 ScrapedProduct，請重試。", level=messages.WARNING)
            return redirect(reverse("admin:game_scrapedproduct_changelist"))

        preview_products, _ = self._build_preview_products(request, products_qs, include_existing_edition=False)

        if request.method == "POST":
            form = ScrapedImportVariantForm(request.POST)
            if form.is_valid():
                language = form.cleaned_data["language"]
                publisher_entity = form.cleaned_data["publisher_entity"]
                is_primary = form.cleaned_data["is_primary"]
                currency = form.cleaned_data.get("currency")
                region = form.cleaned_data.get("region")
                packaging_languages = form.cleaned_data.get("packaging_languages")
                game_title_language = form.cleaned_data.get("game_title_language")

                self._update_normalized_data(request, products_qs, include_barcode=True, include_alternate_name=True)

                created, skipped, errors = 0, 0, []
                for sp in products_qs:
                    c, s, e = _do_import_variant(
                        request, [sp], language, publisher_entity, is_primary,
                        game_title_language=game_title_language,
                        currency=currency, region=region, packaging_languages=packaging_languages,
                    )
                    created += c; skipped += s; errors.extend(e)

                request.session.pop(session_key, None)
                self._flash_results(request, created, skipped, errors)
                return redirect(reverse("admin:game_scrapedproduct_changelist"))
        else:
            form = ScrapedImportVariantForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "匯入 Variant",
            "form": form,
            "products": preview_products,
            "product_ids": product_ids,
            "reviewer_display": self._reviewer_display(request),
        }
        return render(request, "admin/game/scraped_import_variant.html", context)

    def import_bgg_view(self, request):
        session_key = "scraped_import_bgg_ids"
        product_ids = request.POST.getlist("product_ids") if request.method == "POST" else request.session.get(session_key, [])
        products_qs = ScrapedProduct.objects.filter(id__in=product_ids)
        if not products_qs.exists():
            self.message_user(request, "找不到所選的 ScrapedProduct，請重試。", level=messages.WARNING)
            return redirect(reverse("admin:game_scrapedproduct_changelist"))

        preview_products, _ = self._build_preview_products(request, products_qs, include_existing_edition=True)

        if request.method == "POST":
            self._update_normalized_data(request, products_qs, include_barcode=False, include_alternate_name=False)

            thumbnail_choices = {
                str(sp.id): (request.POST.get(f"thumbnail_choice_{sp.id}") or "").strip() or None
                for sp in products_qs
            }
            created, skipped, errors = _do_import_bgg(request, products_qs, thumbnail_choices)

            request.session.pop(session_key, None)
            self._flash_results(request, created, skipped, errors)
            return redirect(reverse("admin:game_scrapedproduct_changelist"))

        context = {
            **self.admin_site.each_context(request),
            "title": "匯入 BGG Data",
            "products": preview_products,
            "product_ids": product_ids,
            "reviewer_display": self._reviewer_display(request),
        }
        return render(request, "admin/game/scraped_import_bgg.html", context)


# ─────────────────────────────────────────────
# Game Suggestion Admin
# ─────────────────────────────────────────────

@admin.register(GameSuggestion)
class GameSuggestionAdmin(admin.ModelAdmin):
    list_display = (
        "name", "rulebook_url_link", "rulebook_url_verified", "barcode",
        "submitted_by", "status", "created_at",
    )
    list_filter = ("status", "rulebook_url_verified")
    search_fields = ("name", "rulebook_url", "barcode")
    readonly_fields = ("reviewed_by", "reviewed_at", "created_at")
    raw_id_fields = ("submitted_by", "reviewed_by", "imported_game")
    actions = ["set_status_approved", "set_status_rejected"]

    @admin.display(description="Rulebook 網址")
    def rulebook_url_link(self, obj):
        if not obj.rulebook_url:
            return "—"
        return format_html('<a href="{0}" target="_blank" rel="noopener">{0}</a>', obj.rulebook_url)

    def _mark_reviewed(self, request, queryset, status):
        from django.utils import timezone

        reviewer = getattr(request.user, "member", None) if request.user.is_authenticated else None
        updated = queryset.update(status=status, reviewed_by=reviewer, reviewed_at=timezone.now())
        self.message_user(
            request,
            f"✅ 已將 {updated} 筆推薦設定為「{status}」",
            level=messages.SUCCESS,
        )

    @admin.action(description="✅ 設定為已核准 (Approved)")
    def set_status_approved(self, request, queryset):
        self._mark_reviewed(request, queryset, GameSuggestionStatus.APPROVED)

    @admin.action(description="🗑️ 設定為已拒絕 (Rejected)")
    def set_status_rejected(self, request, queryset):
        self._mark_reviewed(request, queryset, GameSuggestionStatus.REJECTED)


class EditionImportQueueForm(forms.ModelForm):
    """改成 approved 前先用 run_import 預覽一次，有錯就擋下（變更頁與 list_editable 共用）。"""

    request = None   # admin 的 get_form / get_changelist_form 會掛上，用來檢查權限

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 變更頁的「寫入DB」「skip」按鈕：把 status 改寫成目標值，再走一般的 clean / save_model
        target = None
        if self.request is not None and self.is_bound:
            target = {"_approve": EditionImportQueue.Status.APPROVED,
                      "_skip": EditionImportQueue.Status.SKIP}
            target = next((v for k, v in target.items() if k in self.request.POST), None)
        if target:
            self.data = self.data.copy()
            self.data[self.add_prefix("status")] = target

    class Meta:
        model = EditionImportQueue
        fields = "__all__"
        widgets = {
            "import_text": forms.Textarea(attrs={
                "rows": 30, "spellcheck": "false",
                "style": "width:100%;box-sizing:border-box;font-family:monospace;font-size:13px",
            }),
        }

    def clean(self):
        from .edition_import import run_import

        data = super().clean()
        Q = EditionImportQueue.Status
        if data.get("status") != Q.APPROVED or self.instance.status == Q.APPROVED:
            return data
        if self.request is not None and not self.request.user.has_perm("game.approve_editionimportqueue"):
            raise forms.ValidationError("沒有核准權限，不能寫入DB。")
        text = data.get("import_text", self.instance.import_text) or ""
        if not text.strip():
            raise forms.ValidationError("版本輸入預覽是空的，不能寫入DB（請先到版本輸入頁送審）。")
        report = run_import(text, commit=False)
        if report.has_errors:
            raise forms.ValidationError([
                f"第 {e['line']} 行：{e['text']}" if e["line"] else e["text"] for e in report.errors
            ])
        return data


@admin.register(EditionImportQueue)
class EditionImportQueueAdmin(admin.ModelAdmin):
    form = EditionImportQueueForm
    change_list_template = "admin/game/editionimportqueue/change_list.html"
    change_form_template = "admin/game/editionimportqueue/change_form.html"
    list_display = ("name", "status", "has_text", "import_link", "reviewed_by", "updated_at")
    list_editable = ("status",)
    list_filter = ("status",)
    search_fields = ("name",)
    fields = ("name", "status", "import_text", "reviewed_by", "reviewed_at", "created_at", "updated_at")
    readonly_fields = ("reviewed_by", "reviewed_at", "created_at", "updated_at")

    @admin.display(description="有預覽文字", boolean=True)
    def has_text(self, obj):
        return bool(obj.import_text.strip())

    @admin.display(description="版本輸入")
    def import_link(self, obj):
        if obj.status not in (EditionImportQueue.Status.SEARCHING, EditionImportQueue.Status.REVIEW):
            return "—"
        return format_html('<a href="{}?queue={}">去版本輸入</a>', reverse("admin:game_edition_import"), obj.pk)

    def get_readonly_fields(self, request, obj=None):
        # approved 已寫入 DB，鎖住避免改文字或再切狀態造成重複寫入
        if obj is not None and obj.status == EditionImportQueue.Status.APPROVED:
            return ("name", "status", "import_text") + self.readonly_fields
        return self.readonly_fields

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.request = request
        self._hide_approved_choice(request, form)
        return form

    @staticmethod
    def _hide_approved_choice(request, form):
        """沒有核准權限的人，status 下拉不出現 approved（已是 approved 的列照舊顯示）。"""
        if request.user.has_perm("game.approve_editionimportqueue"):
            return
        field = form.base_fields.get("status")
        if field is not None:
            field.choices = [c for c in field.choices if c[0] != EditionImportQueue.Status.APPROVED]

    def get_changelist_form(self, request, **kwargs):
        # Django 預設的 changelist form 不吃 self.form，要自己帶進去才會跑 clean()
        kwargs.setdefault("form", self.form)
        form = super().get_changelist_form(request, **kwargs)
        form.request = request
        self._hide_approved_choice(request, form)
        return form

    def get_changelist_formset(self, request, **kwargs):
        # approved 的列不能在清單上再改狀態
        formset = super().get_changelist_formset(request, **kwargs)

        class LockedFormSet(formset):
            def add_fields(self2, form, index):
                super().add_fields(form, index)
                if form.instance.pk and form.instance.status == EditionImportQueue.Status.APPROVED:
                    form.fields["status"].disabled = True

        return LockedFormSet

    def save_model(self, request, obj, form, change):
        from .edition_import import run_import

        Q = EditionImportQueue.Status
        was = EditionImportQueue.objects.filter(pk=obj.pk).values_list("status", flat=True).first()
        if obj.status == Q.APPROVED and was != Q.APPROVED:
            report = run_import(obj.import_text, commit=True)
            if report.has_errors:
                # 例如縮圖下載失敗（預覽不下載）：整批已 rollback，狀態退回待approval
                obj.status = Q.REVIEW
                errs = "；".join(e["text"] for e in report.errors)
                messages.error(request, f"「{obj.name}」寫入失敗，已全部還原並退回待approval：{errs}")
            else:
                obj.reviewed_by = getattr(request.user, "member", None)
                obj.reviewed_at = timezone.now()
                messages.success(request, f"「{obj.name}」已寫入 DB。")
        super().save_model(request, obj, form, change)

    def batch_add_view(self, request):
        """一行一個桌遊名，批量建成待search。

        空行與佇列內已有的名稱（不分大小寫）直接略過；名稱若已是既有 Game 的 canonical_name，
        先停下來讓人逐筆選「略過」或「改名」，全部處理完才會寫入。
        """
        from django.core.exceptions import PermissionDenied
        from django.db.models.functions import Lower

        if not self.has_add_permission(request):
            raise PermissionDenied
        names_text = request.POST.get("names", "")
        conflicts = []
        if request.method == "POST":
            # 上一輪的處理選擇：原名(小寫) -> (skip|rename, 新名)
            resolutions = {}
            for key, val in request.POST.items():
                if key.startswith("orig_"):
                    idx = key[5:]
                    resolutions[val.lower()] = (
                        request.POST.get(f"choice_{idx}", "rename"),
                        request.POST.get(f"rename_{idx}", "").strip()[:200],
                    )

            entries = []   # (原名, 最終名)；最終名為 None 代表使用者選擇略過
            for line in names_text.splitlines():
                orig = line.strip()[:200]
                if not orig:
                    continue
                choice, new = resolutions.get(orig.lower(), ("keep", orig))
                entries.append((orig, None if choice == "skip" or not new else new))

            wanted = {n.lower() for _, n in entries if n}
            game_hit = set(
                Game.objects.annotate(l=Lower("canonical_name"))
                .filter(l__in=wanted).values_list("l", flat=True)
            )
            seen = set()
            for orig, name in entries:
                if name and name.lower() in game_hit and orig.lower() not in seen:
                    seen.add(orig.lower())
                    conflicts.append({"orig": orig, "name": name, "renamed": name != orig})

            if not conflicts:
                existing = {n.lower() for n in EditionImportQueue.objects.values_list("name", flat=True)}
                created = skipped = 0
                for _, name in entries:
                    if not name or name.lower() in existing:
                        skipped += 1
                        continue
                    EditionImportQueue.objects.create(name=name)
                    existing.add(name.lower())
                    created += 1
                messages.success(request, f"新增 {created} 筆，略過 {skipped} 筆（重複或已存在而略過）。")
                return redirect("admin:game_editionimportqueue_changelist")

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "批量新增桌遊名",
            "names": names_text,
            "conflicts": conflicts,
        }
        return TemplateResponse(request, "admin/game/editionimportqueue/batch_add.html", context)

    def get_urls(self):
        return [
            path(
                "batch-add/",
                self.admin_site.admin_view(self.batch_add_view),
                name="game_editionimportqueue_batch_add",
            ),
        ] + super().get_urls()


@admin.register(FlowchartSuggestion)
class FlowchartSuggestionAdmin(admin.ModelAdmin):
    """會員在 edition 流程圖分頁留下的改善建議。只讀不改圖，採納與否人工決定。"""

    list_display = (
        "created_at", "edition_name", "ruleset", "content_preview",
        "submitted_by", "status",
    )
    list_filter = ("status", "ruleset")
    search_fields = ("content", "ruleset", "edition__name")
    readonly_fields = (
        "flowchart", "edition", "ruleset", "content", "submitted_by",
        "reviewed_by", "reviewed_at", "created_at",
    )
    raw_id_fields = ("flowchart", "edition", "submitted_by", "reviewed_by")
    actions = ["set_status_approved", "set_status_rejected"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="版本")
    def edition_name(self, obj):
        return obj.edition.name if obj.edition else "—"

    @admin.display(description="建議內容")
    def content_preview(self, obj):
        text = obj.content or ""
        return text if len(text) <= 80 else text[:80] + "…"

    def _mark_reviewed(self, request, queryset, status):
        from django.utils import timezone

        reviewer = getattr(request.user, "member", None) if request.user.is_authenticated else None
        updated = queryset.update(status=status, reviewed_by=reviewer, reviewed_at=timezone.now())
        self.message_user(
            request,
            f"✅ 已將 {updated} 筆建議設定為「{status}」",
            level=messages.SUCCESS,
        )

    @admin.action(description="✅ 設定為已採納 (Approved)")
    def set_status_approved(self, request, queryset):
        self._mark_reviewed(request, queryset, GameSuggestionStatus.APPROVED)

    @admin.action(description="🗑️ 設定為不採納 (Rejected)")
    def set_status_rejected(self, request, queryset):
        self._mark_reviewed(request, queryset, GameSuggestionStatus.REJECTED)


# ─────────────────────────────────────────────
# Game Sync Admin
# ─────────────────────────────────────────────

@admin.register(GameSyncLog)
class GameSyncLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "sync_type", "status_display",
        "records_sent", "media_sent", "qdrant_synced",
        "finished_at",
    )
    list_filter = ("status", "sync_type", "qdrant_synced")
    readonly_fields = (
        "id", "sync_type", "status", "since",
        "records_sent", "media_sent", "qdrant_synced",
        "details_pretty", "error", "created_at", "finished_at",
    )
    ordering = ("-created_at",)
    change_list_template = "admin/game/gamesynclog/change_list.html"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    # ─── Custom URLs for sync buttons ───

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "run-sync/<str:sync_type>/",
                self.admin_site.admin_view(self.run_sync_view),
                name="game_gamesynclog_run_sync",
            ),
        ]
        return custom_urls + urls

    def run_sync_view(self, request, sync_type):
        """Handle the sync button click."""
        if sync_type not in ("delta", "full"):
            messages.error(request, "Invalid sync type")
            return redirect(reverse("admin:game_gamesynclog_changelist"))

        self._execute_sync(request, sync_type)
        return redirect(reverse("admin:game_gamesynclog_changelist"))

    def changelist_view(self, request, extra_context=None):
        """Inject sync buttons into the changelist page."""
        extra_context = extra_context or {}
        delta_url = reverse("admin:game_gamesynclog_run_sync", args=["delta"])
        full_url = reverse("admin:game_gamesynclog_run_sync", args=["full"])
        extra_context["sync_buttons"] = mark_safe(
            f'<div style="margin: 10px 0 15px; display: flex; gap: 10px;">'
            f'<a href="{delta_url}" class="button" '
            f'style="padding: 8px 20px; background: #417690; color: white; '
            f'border-radius: 4px; text-decoration: none; font-weight: bold;" '
            f'onclick="return confirm(\'確定執行 Delta Sync？\')">'
            f'🔄 Delta Sync to VPS</a>'
            f'<a href="{full_url}" class="button" '
            f'style="padding: 8px 20px; background: #ba6d36; color: white; '
            f'border-radius: 4px; text-decoration: none; font-weight: bold;" '
            f'onclick="return confirm(\'確定執行 Full Sync？這會全量同步所有資料。\')">'
            f'📦 Full Sync to VPS</a>'
            f'</div>'
        )
        return super().changelist_view(request, extra_context=extra_context)

    # ─── Display helpers ───

    @admin.display(description="Status")
    def status_display(self, obj):
        colors = {
            "in_progress": "#007BFF",
            "success": "#28A745",
            "partial": "#FFA500",
            "failed": "#DC3545",
        }
        icons = {
            "in_progress": "🔄",
            "success": "✅",
            "partial": "⚠️",
            "failed": "❌",
        }
        color = colors.get(obj.status, "#6C757D")
        icon = icons.get(obj.status, "")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color, icon, obj.get_status_display(),
        )

    @admin.display(description="Details")
    def details_pretty(self, obj):
        if not obj.details:
            return "-"
        formatted = json.dumps(obj.details, indent=2, ensure_ascii=False)
        return format_html("<pre style='max-height:400px;overflow:auto'>{}</pre>", formatted)

    # ─── Sync execution ───

    def _execute_sync(self, request, sync_type):
        from game.sync_service import GameSyncService

        try:
            service = GameSyncService()
            sync_log = service.run(sync_type=sync_type)

            if sync_log.status == "success":
                self.message_user(
                    request,
                    f"✅ Sync 完成！Records: {sync_log.records_sent}, "
                    f"Media: {sync_log.media_sent}, "
                    f"Qdrant: {'✅' if sync_log.qdrant_synced else '❌'}",
                    level=messages.SUCCESS,
                )
            elif sync_log.status == "partial":
                self.message_user(
                    request,
                    f"⚠️ Sync 部分完成。Records: {sync_log.records_sent}, "
                    f"Media: {sync_log.media_sent}. "
                    f"Errors: {sync_log.error[:200]}",
                    level=messages.WARNING,
                )
            else:
                self.message_user(
                    request,
                    f"❌ Sync 失敗: {sync_log.error[:300]}",
                    level=messages.ERROR,
                )
        except Exception as e:
            self.message_user(
                request,
                f"❌ Sync 執行異常: {str(e)[:300]}",
                level=messages.ERROR,
            )


# ─────────────────────────────
# RulebookFlowchart Admin
# ─────────────────────────────

def _next_free_flowchart_ruleset(rulebook_id, base_ruleset, *, force_suffix=False):
    """在指定 rulebook 底下找出一個未被使用的 ruleset 名稱。

    force_suffix=False 時，若 base_ruleset 本身未被使用就直接回傳；
    否則（或 force_suffix=True）在 "<base>-copy" 後面遞增數字直到找到空位。
    """
    if not force_suffix:
        candidate = base_ruleset[:100]
        if not RulebookFlowchart.objects.filter(
            rulebook_id=rulebook_id, ruleset=candidate
        ).exists():
            return candidate

    base = f"{base_ruleset}-copy"
    candidate, i = base, 2
    while RulebookFlowchart.objects.filter(
        rulebook_id=rulebook_id, ruleset=candidate[:100]
    ).exists():
        candidate = f"{base}{i}"
        i += 1
    return candidate[:100]


def node_rulesets(rulebook_id):
    """
    該 rulebook 可用來生成講稿／流程圖的 ruleset 清單（basic 優先，其餘字母序）。

    2026-08 起素材改取 Rulebook.whole_context（全文，沒有 ruleset 維度），所以
    只要有全文就一定給 "basic"。另外把該 rulebook 既有 Script / Flowchart 已在用
    的 ruleset 也併進來，讓人工 duplicate 出來的變體仍然選得到、編輯得到——
    變體一律由人工複製後調整，不自動生成。

    名稱沿用 node_rulesets 是為了不動 7 個呼叫端；它早已不查 RulebookNode。
    """
    from game.models import Rulebook, RulebookScript, RulebookFlowchart

    values = set()
    if Rulebook.objects.filter(pk=rulebook_id).exclude(whole_context="").exists():
        values.add("basic")
    values |= set(
        RulebookScript.objects.filter(rulebook_id=rulebook_id)
        .values_list("ruleset", flat=True).distinct()
    )
    values |= set(
        RulebookFlowchart.objects.filter(rulebook_id=rulebook_id)
        .values_list("ruleset", flat=True).distinct()
    )
    return sorted((v for v in values if v), key=lambda r: (r != "basic", r))


def resolve_node_ruleset(rulebook_id, raw):
    """
    把流程圖的 ruleset 顯示名稱映射回可用的 ruleset；對不上時回傳 None
    （寧可讓呼叫端跳過，也不要建出必定生成失敗的 row）。
    """
    available = node_rulesets(rulebook_id)
    if not available:
        return None
    if raw in available:
        return raw

    # 'Var. 1: Tactics' → 'tactics'、'Two Player' → 'two_player'
    slug = re.sub(r"^var\.?\s*\d+\s*:\s*", "", (raw or "").strip(), flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")
    if slug in available:
        return slug
    if slug in ("", "default") and "basic" in available:
        return "basic"
    # 全文模式下所有 ruleset 拿到的素材都一樣，對不上就退回 basic
    return "basic" if "basic" in available else None


class CopyFlowchartToEditionForm(forms.Form):
    target_edition = forms.ModelChoiceField(
        queryset=Edition.objects.select_related("game").all(),
        label="Target Edition",
        help_text="搜尋並選擇要複製到的 Edition（可為不同 game）。",
    )

    def __init__(self, *args, admin_site=None, **kwargs):
        super().__init__(*args, **kwargs)
        if admin_site is not None:
            field = self.fields["target_edition"]
            field.widget = AutocompleteSelect(
                RulebookFlowchart._meta.get_field("edition"), admin_site
            )
            # ModelChoiceField.__init__ 已把 choices 綁到「舊」widget；換 widget 後
            # 需重新指派，否則 Select.optgroups() 會拿到空 tuple 而非 ModelChoiceIterator。
            field.widget.choices = field.choices


class FlowchartReviewStatusFilter(admin.SimpleListFilter):
    """
    審核狀態篩選。判準與 flowchart_review.review_state() 一致，但用 SQL 表達，
    不逐筆讀 log：比對草稿 content_hash 與公開版、最新一筆審核紀錄的 hash。
    """
    title = "審核狀態"
    parameter_name = "review"

    def lookups(self, request, model_admin):
        from game.flowchart_review import STATE_LABELS
        return list(STATE_LABELS.items())

    def queryset(self, request, queryset):
        from django.db.models import F, OuterRef, Q, Subquery
        from game.flowchart_review import State

        value = self.value()
        if not value:
            return queryset

        latest = FlowchartReview.objects.filter(flowchart=OuterRef("pk")).order_by("-created_at")
        qs = queryset.annotate(
            _latest_action=Subquery(latest.values("action")[:1]),
            _latest_hash=Subquery(latest.values("content_hash")[:1]),
        )
        live = Q(publication__is_live=True)
        live_same = live & Q(publication__content_hash=F("content_hash"))
        latest_is_current = Q(_latest_hash=F("content_hash"))
        submitted = latest_is_current & Q(_latest_action=FlowchartReview.Action.SUBMITTED)
        rejected = latest_is_current & Q(_latest_action=FlowchartReview.Action.REJECTED)

        if value == State.LIVE:
            return qs.filter(live_same)
        qs = qs.exclude(live_same)
        if value == State.PENDING:
            return qs.filter(submitted)
        if value == State.REJECTED:
            return qs.filter(rejected)
        qs = qs.exclude(submitted).exclude(rejected)
        if value == State.LIVE_WITH_CHANGES:
            return qs.filter(live)
        if value == State.DRAFT:
            return qs.exclude(live)
        return queryset


@admin.register(RulebookFlowchart)
class RulebookFlowchartAdmin(admin.ModelAdmin):
    list_display = (
        "rulebook_title", "ruleset", "display_order", "initial",
        "node_count", "linkage_count", "review_status",
        # "error_check_summary", "self_check_summary",
        "updated_at",
    )
    # 拿掉過的欄（別再加回來，欄位本身仍在用，只是列表上沒有鑑別力）：
    # - Adjusted：工作流是「生成→進編輯器調整→送審→核准」，所以每張上線的圖必然
    #   adjusted_json is not None，這格永遠是勾，等於跟審核狀態重複。
    #   （adjusted_json 欄位本身照舊是顯示用的實際內容，見 selectors.get_edition_flowchart。）
    # - Translation：translation_status 欄位已移除。公開頁根本不讀它（localize()
    #   一律執行，查無譯文逐句退回原文），而且譯文快取以 text_hash 全站共用，翻 A 圖會
    #   順便補完 B 圖的譯文卻不更新 B 的狀態，所以這個值必然飄。
    # prompt_version、llm_model 兩欄已從列表隱藏（準備淘汰）。欄位本身保留，免得為此
    # 改 models.py 做 migration；右側篩選器暫時還在。
    list_editable = ("display_order",)
    list_filter = (
        FlowchartReviewStatusFilter,
        "ruleset", "initial",
    )

    def get_queryset(self, request):
        from django.db.models import Func, IntegerField, Value
        from django.db.models.fields.json import KeyTransform
        from django.db.models.functions import Coalesce

        def array_len(field, key):
            return Func(
                KeyTransform(key, field), function="jsonb_array_length",
                output_field=IntegerField(),
            )

        # 與 node_count 顯示的同一份內容（adjusted 優先，否則 react_flow_json），
        # 節點數 + 連線數，給「Nodes」欄排序用。
        def effective_len(key):
            return Coalesce(
                array_len("adjusted_json", key), array_len("react_flow_json", key), Value(0),
            )

        return super().get_queryset(request).select_related("publication").annotate(
            _linked_count=models.Count("linked_editions", distinct=True),
            _size=effective_len("nodes") + effective_len("edges"),
        )

    @admin.display(description="Linked", ordering="_linked_count")
    def linkage_count(self, obj):
        return obj._linked_count or "-"

    _REVIEW_BADGE_COLORS = {
        "draft": "#888",
        "pending": "#d46b08",
        "rejected": "#cf1322",
        "live": "#389e0d",
        "live_with_changes": "#1677ff",
    }

    @admin.display(description="審核")
    def review_status(self, obj):
        from game.flowchart_review import STATE_LABELS, review_state
        state = review_state(obj)
        return format_html(
            '<span style="color:{};white-space:nowrap">● {}</span>',
            self._REVIEW_BADGE_COLORS.get(state, "#888"), STATE_LABELS[state],
        )

    actions = (
        "add_missing_text_items",
        "duplicate_selected", "copy_to_edition", "link_to_edition",
        "create_script_from_flowchart",
        "unpublish_selected",
        "shrink_nodes_to_fit", "translate_selected", "force_translate_selected", "check_flowchart_errors", "check_flowchart_standalone",
    )

    # 刻意沒有「批次核准」：核准一定要進審核頁看過草稿與差異（見 review_view）。
    def has_review_permission(self, request):
        from game.flowchart_review import can_review
        return can_review(request.user)

    @admin.action(description="🚫 下架（公開頁不再顯示，需 reviewer 權限）", permissions=["review"])
    def unpublish_selected(self, request, queryset):
        from game.flowchart_review import ReviewError, unpublish
        done = skipped = 0
        for chart in queryset:
            try:
                unpublish(chart, request.user)
                done += 1
            except ReviewError:
                skipped += 1
        self.message_user(
            request, f"已下架 {done} 張，略過 {skipped} 張（本來就沒有公開）。",
            level=messages.SUCCESS if done else messages.WARNING,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/review/",
                self.admin_site.admin_view(self.review_view),
                name="game_rulebookflowchart_review",
            ),
            path(
                "<path:object_id>/submit-review/",
                self.admin_site.admin_view(self.submit_review_view),
                name="game_rulebookflowchart_submit_review",
            ),
            path(
                "<path:object_id>/restore-published/",
                self.admin_site.admin_view(self.restore_published_view),
                name="game_rulebookflowchart_restore_published",
            ),
            path(
                "<path:object_id>/withdraw-review/",
                self.admin_site.admin_view(self.withdraw_review_view),
                name="game_rulebookflowchart_withdraw_review",
            ),
        ]
        return custom_urls + urls

    def submit_review_view(self, request, object_id):
        """編輯者送審（POST only）。"""
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseNotAllowed
        from game.flowchart_review import ReviewError, can_edit, submit

        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not can_edit(request.user):
            raise PermissionDenied
        chart = self.get_object(request, object_id)
        if chart is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)
        try:
            submit(chart, request.user, comment=request.POST.get("comment", ""))
            self.message_user(request, "已送審，等待 reviewer 確認。", level=messages.SUCCESS)
        except ReviewError as e:
            self.message_user(request, str(e), level=messages.WARNING)
        return redirect(reverse("admin:game_rulebookflowchart_change", args=[chart.pk]))

    def restore_published_view(self, request, object_id):
        """編輯者把草稿還原成目前公開版（POST only）。"""
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseNotAllowed
        from game.flowchart_review import ReviewError, can_edit, restore_published

        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not can_edit(request.user):
            raise PermissionDenied
        chart = self.get_object(request, object_id)
        if chart is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)
        try:
            restore_published(chart, request.user)
            self.message_user(request, "已將草稿還原為目前的公開版。", level=messages.SUCCESS)
        except ReviewError as e:
            self.message_user(request, str(e), level=messages.WARNING)
        return redirect(reverse("admin:game_rulebookflowchart_change", args=[chart.pk]))

    def withdraw_review_view(self, request, object_id):
        """編輯者收回送審（POST only）。"""
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponseNotAllowed
        from game.flowchart_review import ReviewError, can_edit, withdraw

        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not can_edit(request.user):
            raise PermissionDenied
        chart = self.get_object(request, object_id)
        if chart is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)
        try:
            withdraw(chart, request.user)
            self.message_user(request, "已收回送審，可以繼續編輯。", level=messages.SUCCESS)
        except ReviewError as e:
            self.message_user(request, str(e), level=messages.WARNING)
        return redirect(reverse("admin:game_rulebookflowchart_change", args=[chart.pk]))

    def review_view(self, request, object_id):
        """
        reviewer 的審核頁：草稿與公開版並排、文字差異、LLM 檢查結果、審核歷史。
        核准／退回都帶 expected_hash：reviewer 看到的版本若在送出前被改過就拒絕。
        """
        from django.core.exceptions import PermissionDenied
        from game import flowchart_review as fr
        from game.rag.flowchart.i18n import resolve_translation_status

        if not fr.can_review(request.user):
            raise PermissionDenied
        chart = self.get_object(request, object_id)
        if chart is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)

        if request.method == "POST":
            decision = request.POST.get("decision")
            expected = request.POST.get("expected_hash", "")
            comment = request.POST.get("comment", "").strip()
            try:
                if decision == "approve":
                    fr.approve(chart, request.user, expected, comment)
                    self.message_user(request, "✅ 已核准並發布，公開頁改為顯示這一版。", level=messages.SUCCESS)
                elif decision == "reject":
                    fr.reject(chart, request.user, expected, comment)
                    self.message_user(request, "已退回。", level=messages.SUCCESS)
                elif decision == "unpublish":
                    fr.unpublish(chart, request.user, comment)
                    self.message_user(request, "已下架。", level=messages.SUCCESS)
                else:
                    self.message_user(request, "未知的操作。", level=messages.ERROR)
                return redirect(reverse("admin:game_rulebookflowchart_change", args=[chart.pk]))
            except fr.ReviewError as e:
                self.message_user(request, str(e), level=messages.ERROR)
                return redirect(reverse("admin:game_rulebookflowchart_review", args=[chart.pk]))

        pub = fr.get_publication(chart)
        live_content = pub.content if pub and pub.is_live else None
        draft = chart.effective_json
        diff = fr.text_diff(live_content, draft)

        viewer_configs = [{
            "mountId": "fc-review-draft",
            "reactFlowData": draft,
            "detail": chart.detail,
            "rulebookTitle": chart.rulebook.title,
            "isAdjusted": True,
            "readOnly": True,
        }]
        if live_content:
            viewer_configs.append({
                "mountId": "fc-review-live",
                "reactFlowData": live_content,
                "detail": chart.detail,
                "rulebookTitle": chart.rulebook.title,
                "isAdjusted": True,
                "readOnly": True,
            })

        return TemplateResponse(
            request,
            "admin/game/rulebookflowchart/review.html",
            {
                **self.admin_site.each_context(request),
                "title": f"審核流程圖：{chart.rulebook.title}（{chart.ruleset}）",
                "opts": self.opts,
                "original": chart,
                "state": fr.review_state(chart),
                "state_label": fr.STATE_LABELS[fr.review_state(chart)],
                "publication": pub,
                "has_live": bool(live_content),
                "same_as_live": bool(live_content) and pub.content_hash == chart.content_hash,
                "is_empty": not draft,
                "diff": diff,
                "viewer_configs": viewer_configs,
                "translation_done": resolve_translation_status(draft) == "done",
                "reviews": chart.reviews.select_related("actor", "last_editor")[:20],
                "preview_urls": fr.preview_urls(chart) if draft else [],
            },
        )

    @admin.action(description="⧉ Duplicate selected flowcharts")
    def duplicate_selected(self, request, queryset):
        created = 0
        for src in queryset:
            candidate = _next_free_flowchart_ruleset(src.rulebook_id, src.ruleset, force_suffix=True)
            RulebookFlowchart.objects.create(
                rulebook_id=src.rulebook_id,
                edition_id=src.edition_id,
                ruleset=candidate,
                initial=src.initial,
                display_order=src.display_order,
                detail=src.detail,
                intermediate_json=src.intermediate_json,
                source_chunk_ids=src.source_chunk_ids,
                react_flow_json=src.react_flow_json,
                adjusted_json=src.adjusted_json,
                # 不帶發布狀態：複製出來的圖是新草稿，要重新送審
                content_edited_by=request.user,
                content_edited_at=timezone.now(),
                translated_at=src.translated_at,
                llm_model=src.llm_model,
                prompt_version=src.prompt_version,
            )
            created += 1
        self.message_user(request, f"Duplicated {created} flowchart(s).", level=messages.SUCCESS)

    @admin.action(description="📋 Copy to edition")
    def copy_to_edition(self, request, queryset):
        if "apply_copy" in request.POST:
            form = CopyFlowchartToEditionForm(request.POST, admin_site=self.admin_site)
            if form.is_valid():
                target_edition = form.cleaned_data["target_edition"]
                created_charts = created_rulebooks = 0
                for src in queryset:
                    with transaction.atomic():
                        rulebook = target_edition.rulebooks.first()
                        if rulebook is None:
                            rulebook = Rulebook.objects.create(
                                edition=target_edition,
                                language=target_edition.language or src.rulebook.language,
                                title=(
                                    f"{target_edition.name or target_edition.game.canonical_name} "
                                    "— flowchart placeholder"
                                )[:200],
                            )
                            created_rulebooks += 1
                        ruleset = _next_free_flowchart_ruleset(
                            rulebook.id, src.ruleset, force_suffix=False
                        )
                        RulebookFlowchart.objects.create(
                            rulebook=rulebook,
                            edition=target_edition,
                            ruleset=ruleset,
                            initial=src.initial,
                            display_order=src.display_order,
                            detail=src.detail,
                            intermediate_json=src.intermediate_json,
                            source_chunk_ids=src.source_chunk_ids,
                            react_flow_json=src.react_flow_json,
                            adjusted_json=src.adjusted_json,
                            # 不帶發布狀態：複製到別的 edition 的圖要重新送審
                            content_edited_by=request.user,
                            content_edited_at=timezone.now(),
                            translated_at=src.translated_at,
                            llm_model=src.llm_model,
                            prompt_version=src.prompt_version,
                        )
                        created_charts += 1
                msg = f"Copied {created_charts} flowchart(s) to '{target_edition}'."
                if created_rulebooks:
                    msg += f" Created {created_rulebooks} placeholder rulebook(s)."
                self.message_user(request, msg, level=messages.SUCCESS)
                return None
        else:
            form = CopyFlowchartToEditionForm(admin_site=self.admin_site)

        return TemplateResponse(
            request,
            "admin/game/rulebookflowchart/copy_to_edition_confirm.html",
            {
                **self.admin_site.each_context(request),
                "title": "Copy flowchart(s) to edition",
                "queryset": queryset,
                "form": form,
                "opts": self.model._meta,
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
            },
        )

    @admin.action(description="🔗 Link to edition (share, no copy)")
    def link_to_edition(self, request, queryset):
        if "apply_link" in request.POST:
            form = CopyFlowchartToEditionForm(request.POST, admin_site=self.admin_site)
            if form.is_valid():
                from django.utils import timezone

                target_edition = form.cleaned_data["target_edition"]
                linked_pks = []
                for src in queryset:
                    src.linked_editions.add(target_edition)
                    linked_pks.append(src.pk)
                linked = len(linked_pks)
                # m2m 的 add() 不會動到 updated_at（auto_now 只在 save() 觸發），
                # 但 delta sync 是靠 updated_at__gt=since 挑出要送的記錄
                # （sync_service._collect_db_records）。不手動推進時間戳的話，
                # 這裡建立的共用關係永遠不會同步到 VPS。
                if linked_pks:
                    self.model.objects.filter(pk__in=linked_pks).update(
                        updated_at=timezone.now()
                    )
                self.message_user(
                    request,
                    f"Linked {linked} flowchart(s) to '{target_edition}' (shared, not copied).",
                    level=messages.SUCCESS,
                )
                return None
        else:
            form = CopyFlowchartToEditionForm(admin_site=self.admin_site)

        return TemplateResponse(
            request,
            "admin/game/rulebookflowchart/link_to_edition_confirm.html",
            {
                **self.admin_site.each_context(request),
                "title": "Link flowchart(s) to edition",
                "queryset": queryset,
                "form": form,
                "opts": self.model._meta,
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
            },
        )

    @admin.action(description="❌📐 依文字長度縮到最小尺寸（先預覽）")
    def shrink_nodes_to_fit(self, request, queryset):
        """
        依每個節點的實際文字算出剛好裝得下的最小外框（取 6 語最寬者），
        中心點不動。先出確認頁預覽，按下確認才寫回 adjusted_json。
        """
        from game.rag.flowchart.autosize import (
            apply_resize, plan_resize, preview_group_growth,
        )

        rows = []            # 有可改的圖
        skipped_auto = []    # 還沒在編輯器存過
        skipped_same = []    # 已經是最小尺寸
        for chart in queryset:
            # adjusted_json is None 的圖所有 position 都是 (0,0)，前端每次載入
            # 都重跑 dagre，而 dagre 用自己的 180×60 假設（layout.ts）不看 style。
            # 對它寫尺寸只會讓間距估算更歪，所以直接略過。
            if not chart.adjusted_json:
                skipped_auto.append(chart)
                continue
            plans = plan_resize(chart.adjusted_json)
            changed = [p for p in plans if p.changed]
            if not changed:
                skipped_same.append(chart)
                continue
            rows.append({
                "chart": chart,
                "plans": changed,
                "node_count": len(plans),
                "grew_count": sum(1 for p in changed if p.grew),
                "avg_pct": round(
                    sum(p.delta_pct for p in changed) / len(changed)
                ),
                # 節點改尺寸後凸出相位外框的話，React Flow 的 extent:"parent"
                # 會把它夾回去（等於默默打亂排版），所以外框會跟著放大。
                "groups": preview_group_growth(chart.adjusted_json, changed),
            })

        if "apply_shrink" in request.POST:
            from game.flowchart_review import EDIT_FIELDS, mark_edited

            done = nodes_done = 0
            for row in rows:
                chart = row["chart"]
                chart.adjusted_json = apply_resize(chart.adjusted_json, row["plans"])
                mark_edited(chart, request.user)
                chart.save(update_fields=["adjusted_json", "updated_at", *EDIT_FIELDS])
                done += 1
                nodes_done += len(row["plans"])
            self.message_user(
                request,
                f"📐 已調整 {done} 張流程圖、共 {nodes_done} 個節點。"
                + (f"（略過 {len(skipped_auto) + len(skipped_same)} 張）"
                   if skipped_auto or skipped_same else ""),
                level=messages.SUCCESS if done else messages.WARNING,
            )
            return None

        return TemplateResponse(
            request,
            "admin/game/rulebookflowchart/shrink_nodes_confirm.html",
            {
                **self.admin_site.each_context(request),
                "title": "依文字長度縮到最小尺寸",
                "queryset": queryset,
                "rows": rows,
                "skipped_auto": skipped_auto,
                "skipped_same": skipped_same,
                "total_nodes": sum(len(r["plans"]) for r in rows),
                "opts": self.model._meta,
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
            },
        )

    def _report_translation_result(self, request, label, ok, fail, problems):
        """
        把翻譯結果講清楚。翻譯失敗在這條管線裡是靜默的（公開頁 localize 查無譯文
        會退回原文），所以失敗時一定要把是哪張圖、缺哪些語言直接列在 admin 訊息上，
        不能只留一句「失敗 N 張」讓人回頭翻 log。
        """
        if not fail:
            self.message_user(request, f"{label}完成：成功 {ok} 張。", level=messages.SUCCESS)
            return

        detail = "；".join(problems[:5])
        if len(problems) > 5:
            detail += f"；…另有 {len(problems) - 5} 張（詳見 log）"
        self.message_user(
            request,
            f"⚠️ {label}：成功 {ok} 張，失敗 {fail} 張。{detail}",
            level=messages.ERROR,
        )

    @admin.action(description="❌🆕補譯缺漏（僅翻譯選取的流程圖，節省流量且維持穩定）")
    def translate_selected(self, request, queryset):
        from django.utils import timezone
        from game.rag.flowchart.i18n import collect_texts, ensure_translations

        ok = fail = 0
        problems = []
        for chart in queryset:
            try:
                rb = chart.rulebook
                src = rb.language.language if rb.language_id else "en"
                effective = chart.adjusted_json or chart.react_flow_json
                # force=False：僅翻譯不存在快取的文字
                report = ensure_translations(collect_texts(effective or {}), src, force=False)
                # ruleset 名稱是固定的英文識別詞（basic/variant...），與 rulebook 語言無關
                report.merge(ensure_translations([chart.ruleset], "en", force=False))
                # 翻譯失敗是靜默的（localize 會退回原文），所以只有 report.ok 才記翻譯時間。
                if report.ok:
                    chart.translated_at = timezone.now()
                    chart.save(update_fields=["translated_at", "updated_at"])
                    ok += 1
                else:
                    fail += 1
                    problems.append(f"{chart}：{report.describe()}")
            except Exception as exc:
                logger.exception("flowchart 翻譯失敗：%s", chart.id)
                fail += 1
                problems.append(f"{chart}：{type(exc).__name__} {exc}")
        self._report_translation_result(request, "補譯", ok, fail, problems)

    @admin.action(description="📝補文字項（只在 Flowchart text 新增缺少的項目，不翻譯）")
    def add_missing_text_items(self, request, queryset):
        from game.rag.flowchart.i18n import collect_texts, compute_hash, _norm_lang

        # hash -> (原文, 來源語)；同一段文字以第一次出現的來源語為準
        wanted = {}
        for chart in queryset.select_related("rulebook__language"):
            rb = chart.rulebook
            src = _norm_lang(rb.language.language if rb.language_id else "en")
            effective = chart.adjusted_json or chart.react_flow_json
            for t in collect_texts(effective or {}):
                if t and t.strip():
                    wanted.setdefault(compute_hash(t), (t, src))
            # ruleset 名稱是固定的英文識別詞，與 rulebook 語言無關
            if chart.ruleset and chart.ruleset.strip():
                wanted.setdefault(compute_hash(chart.ruleset), (chart.ruleset, "en"))

        existing = set(
            FlowchartTextTranslation.objects.filter(
                text_hash__in=list(wanted.keys())
            ).values_list("text_hash", flat=True)
        )
        new_rows = [
            # translations 只放來源語原文；其他語言留空，之後用「補譯缺漏」補齊
            FlowchartTextTranslation(
                text_hash=h, source_text=t, source_lang=src, translations={src: t},
            )
            for h, (t, src) in wanted.items()
            if h not in existing
        ]
        FlowchartTextTranslation.objects.bulk_create(new_rows, ignore_conflicts=True)
        self.message_user(
            request,
            f"新增 {len(new_rows)} 筆文字項，略過 {len(wanted) - len(new_rows)} 筆（已存在）。未做翻譯。",
        )

    @admin.action(description="❌⚠️強制重譯（重新翻譯選取的流程圖，保留人工修改項目）")
    def force_translate_selected(self, request, queryset):
        from django.utils import timezone
        from game.rag.flowchart.i18n import collect_texts, ensure_translations

        ok = fail = 0
        problems = []
        for chart in queryset:
            try:
                rb = chart.rulebook
                src = rb.language.language if rb.language_id else "en"
                effective = chart.adjusted_json or chart.react_flow_json
                # force=True：刪除 is_manual=False 的舊快取並重譯
                report = ensure_translations(collect_texts(effective or {}), src, force=True)
                # ruleset 名稱是固定的英文識別詞（basic/variant...），與 rulebook 語言無關
                report.merge(ensure_translations([chart.ruleset], "en", force=True))
                # 同 translate_selected：翻譯失敗不記翻譯時間。
                if report.ok:
                    chart.translated_at = timezone.now()
                    chart.save(update_fields=["translated_at", "updated_at"])
                    ok += 1
                else:
                    fail += 1
                    problems.append(f"{chart}：{report.describe()}")
            except Exception as exc:
                logger.exception("flowchart 強制翻譯失敗：%s", chart.id)
                fail += 1
                problems.append(f"{chart}：{type(exc).__name__} {exc}")
        self._report_translation_result(request, "強制重譯", ok, fail, problems)

    @admin.action(description=f"❌🔍 對照 rulebook 全文檢查流程圖（LLM，{GEMINI_MAIN_MODEL}）")
    def check_flowchart_errors(self, request, queryset):
        from game.rag.flowchart.check import check_flowchart

        self._run_flowchart_check(
            request, queryset, runner=check_flowchart,
            result_field="error_check_result", at_field="error_checked_at",
            icon="🔍", model=None,
        )

    @admin.action(description=f"❌🧩 獨立檢查流程圖（不看 rulebook，LLM，{GEMINI_MAIN_MODEL}）")
    def check_flowchart_standalone(self, request, queryset):
        """跟上面那個職責正交：不給 rulebook，只問這張圖自身夠不夠玩。"""
        from game.rag.flowchart.selfcheck import check_flowchart_standalone

        self._run_flowchart_check(
            request, queryset, runner=check_flowchart_standalone,
            result_field="self_check_result", at_field="self_checked_at",
            icon="🧩", model=None,
        )

    def _run_flowchart_check(self, request, queryset, runner, result_field, at_field,
                             icon="🔍", model=None):
        """
        runner(flowchart_id, model=...) 回傳 {issues, summary, model, usage}，
        結果寫進 result_field / at_field。
        model=None 用 runner 的 Gemini 預設模型（GEMINI_MAIN_MODEL）。
        """
        from game.rag.flowchart.check import FlowchartCheckError

        for chart in queryset:
            title = f"{chart.rulebook.title} ({chart.ruleset})"
            try:
                result = runner(str(chart.id), model=model)
            except FlowchartCheckError as e:
                self.message_user(request, f"⏭ '{title}'：{e}", level=messages.WARNING)
                continue
            except Exception:
                logger.exception("flowchart 錯誤檢查失敗：%s", chart.id)
                self.message_user(request, f"❌ '{title}' 檢查失敗，詳見 log。", level=messages.ERROR)
                continue

            from django.utils import timezone
            setattr(chart, result_field, result)
            setattr(chart, at_field, timezone.now())
            chart.save(update_fields=[result_field, at_field, "updated_at"])

            issues = result.get("issues") or []
            summary = result.get("summary") or ""
            usage = result.get("usage") or {}
            prompt_tk = usage.get("prompt_tokens", 0)
            completion_tk = usage.get("completion_tokens", 0)
            total_tk = usage.get("total_tokens", 0)
            cached_tk = usage.get("cached_tokens", 0)
            token_line = (
                f"🔢 token：prompt {prompt_tk:,}"
                + (f"（含 cached {cached_tk:,}）" if cached_tk else "")
                + f" + completion {completion_tk:,} = {total_tk:,}"
            )

            if not issues:
                self.message_user(
                    request,
                    format_html("✅ '{}'：未發現問題。{}<br>{}", title, summary, token_line),
                    level=messages.SUCCESS,
                )
                continue

            error_issues = [i for i in issues if i.get("severity") == "error"]
            lines = [
                f"{'❗' if i.get('severity') == 'error' else '⚠️'}"
                f"{'🔧' if i.get('source') == 'structure' else ''} "
                f"[{i.get('location') or '-'}] {i.get('description', '')}"
                for i in issues[:8]
            ]
            if len(issues) > 8:
                lines.append(f"…還有 {len(issues) - 8} 項未列出")
            lines.append(token_line)
            self.message_user(
                request,
                format_html(
                    "{} '{}'：發現 {} 個錯誤、{} 個警告。{}<br>{}",
                    icon, title, len(error_issues), len(issues) - len(error_issues), summary,
                    format_html_join(mark_safe("<br>"), "{}", ((l,) for l in lines)),
                ),
                level=messages.ERROR if error_issues else messages.WARNING,
            )

    @admin.action(description="🎙 Create script from this flowchart")
    def create_script_from_flowchart(self, request, queryset):
        created_or_found = []
        for fc in queryset:
            # fc.ruleset 可能是顯示名稱（'Default'、'Var. 1: Tactics'），必須映射回
            # node 的 ruleset，否則 ScriptService 撈不到素材、生成必然失敗。
            ruleset = resolve_node_ruleset(fc.rulebook_id, fc.ruleset)
            if ruleset is None:
                self.message_user(
                    request,
                    f"⏭ 略過 '{fc.rulebook.title}'（{fc.ruleset}）："
                    f"找不到對應的 RulebookNode ruleset，可選的有 "
                    f"{node_rulesets(fc.rulebook_id) or '（無，請先執行 💫1️⃣Extract by LlamaParse）'}。",
                    level=messages.WARNING,
                )
                continue
            obj, created = RulebookScript.objects.get_or_create(
                rulebook_id=fc.rulebook_id, ruleset=ruleset,
                language=fc.rulebook.language,
                defaults=dict(edition_id=fc.edition_id, source_flowchart=fc),
            )
            if not created and obj.source_flowchart_id != fc.id:
                obj.source_flowchart = fc
                obj.save(update_fields=["source_flowchart", "updated_at"])
            created_or_found.append((obj, created))

        if not created_or_found:
            return

        if len(created_or_found) == 1:
            obj, created = created_or_found[0]
            verb = "Created" if created else "Found existing"
            self.message_user(request, f"{verb} script draft — 請填寫 host_persona / story_atmosphere 後生成。", level=messages.SUCCESS)
            return redirect(reverse("admin:game_rulebookscript_change", args=[obj.pk]))

        made = sum(1 for _, c in created_or_found if c)
        found = len(created_or_found) - made
        self.message_user(
            request,
            f"✅ Created {made} script draft(s), {found} already existed. 請到 RulebookScript 逐一填寫 persona/atmosphere。",
            level=messages.SUCCESS,
        )

    search_fields = ("rulebook__title", "rulebook__edition__game__canonical_name")
    ordering = ("-updated_at",)
    autocomplete_fields = ("rulebook", "linked_editions")
    readonly_fields = (
        "id", "edition", "detail",
        "prompt_version", "llm_model", "created_at", "updated_at",
        "node_count",
        "react_flow_json_display",
        "error_check_display",
        "self_check_display",
    )

    fieldsets = (
        ("圖表資訊", {
            "fields": ("rulebook", "ruleset", "display_order", "initial"),
            "description": "「Initial」＝入門圖：一般會員與未登入者看得到內容。"
                           "取消勾選的圖只有 subscriber（含 admin）看得到，其他人"
                           "在流程圖分頁只會看到 ruleset 名稱與付費牆。"
                           "公開與否不在這裡設定：圖的內容要經 reviewer 在審核頁核准才會上線。",
        }),
        ("共用連結", {
            "fields": ("linked_editions",),
            "description": "直接讓其他 edition 共用顯示本圖（不複製資料）。例如同一遊戲的不同語言版本共用同一張流程圖；日後修改本圖會同步反映在所有連結的 edition 上。",
        }),
        # 「對照 rulebook 全文檢查結果」「獨立自足性檢查結果」兩個區塊已從編輯頁隱藏
        # （準備淘汰）。欄位（error_check_*／self_check_*）與顯示方法保留，免得為此
        # 改 models.py 做 migration；審核頁、列表欄位與檢查 action 暫時還在。
        ("React Flow JSON", {
            "fields": ("react_flow_json_display",),
            "classes": ("collapse",)
        }),
        ("系統", {
            "fields": ("id", "edition", "detail", "prompt_version", "llm_model", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def has_add_permission(self, request):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        try:
            obj = self.get_object(request, object_id)
            if obj:
                from game import flowchart_review as fr
                state = fr.review_state(obj)
                pub = fr.get_publication(obj)
                extra_context.update({
                    "review_state": state,
                    "review_state_label": fr.STATE_LABELS[state],
                    "review_publication": pub if pub and pub.is_live else None,
                    "review_can_submit": fr.can_edit(request.user) and state in (
                        fr.State.DRAFT, fr.State.REJECTED, fr.State.LIVE_WITH_CHANGES,
                    ) and bool(obj.content_hash),
                    "review_can_withdraw": fr.can_edit(request.user) and state == fr.State.PENDING,
                    "review_can_restore": fr.can_edit(request.user) and bool(
                        pub and pub.is_live and pub.content_hash != obj.content_hash
                    ),
                    "review_can_review": fr.can_review(request.user),
                    "review_recent": obj.reviews.select_related("actor", "last_editor")[:5],
                    "preview_urls": fr.preview_urls(obj) if obj.content_hash else [],
                })
                if request.user.has_perm("game.change_flowcharttexttranslation") and obj.content_hash:
                    from game.rag.flowchart.i18n import pending_translations
                    extra_context["text_pending_count"] = len(pending_translations([obj])[obj.pk])
                    extra_context["text_batch_url"] = reverse(
                        "admin:game_flowcharttexttranslation_translate_chart", args=[obj.pk],
                    )

                # Backfill react_flow_json from intermediate_json for flowcharts
                # generated before migration 0081 (react_flow_json was empty {})
                rf_data = obj.react_flow_json
                if not rf_data and obj.intermediate_json:
                    from game.rag.flowchart.schemas import FlowGraph
                    from game.rag.flowchart.reactflow import to_react_flow
                    try:
                        graph = FlowGraph.from_dict(obj.intermediate_json)
                        rf_data = to_react_flow(graph)
                        obj.react_flow_json = rf_data
                        obj.save(update_fields=["react_flow_json"])
                    except Exception as e:
                        logger.warning(f"[Admin] Failed to backfill react_flow_json for {obj.id}: {e}")
                        rf_data = None

                # 空白 flowchart（admin action 建立）沒有任何內容：給編輯器一個空骨架，
                # 否則前端判定「No flowchart data」，整個 toolbar 都不會渲染。
                if not rf_data and not obj.adjusted_json:
                    rf_data = {"nodes": [], "edges": []}

                # ruleset 是自由文字，可能含 + & # % 空白等在 query string 有特殊
                # 意義的字元（`+` 會被解成空白），必須 percent-encode，否則後端
                # 以 (rulebook, ruleset) 定位時查無資料 → 存檔一律 404。
                from urllib.parse import quote
                adjust_url = (
                    f"/api/game/rulebooks/{obj.rulebook_id}/flowchart/adjust/"
                    f"?ruleset={quote(obj.ruleset or '', safe='')}"
                )
                extra_context["adjust_url"] = adjust_url
                extra_context["react_flow_json"] = (
                    mark_safe(json.dumps(rf_data)) if rf_data else "null"
                )
                extra_context["adjusted_json"] = (
                    mark_safe(json.dumps(obj.adjusted_json)) if obj.adjusted_json else "null"
                )
                extra_context["rulebook_title_json"] = mark_safe(
                    json.dumps(obj.rulebook.title)
                )
                try:
                    extra_context["game_name_json"] = mark_safe(
                        json.dumps(obj.rulebook.edition.name)
                    )
                except Exception:
                    extra_context["game_name_json"] = "null"
                try:
                    ed = obj.rulebook.edition
                    thumb_url = ed.thumbnail.url if ed.thumbnail else None
                    extra_context["thumbnail_url_json"] = mark_safe(json.dumps(thumb_url))
                except Exception:
                    extra_context["thumbnail_url_json"] = "null"
        except Exception:
            pass
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.display(description="Rulebook", ordering="rulebook__title")
    def rulebook_title(self, obj):
        return obj.rulebook.title

    @staticmethod
    def _check_summary_cell(result, checked_at):
        """changelist 上的 errors(warnings) 小格，兩種檢查共用。"""
        if not checked_at:
            return "—"
        issues = (result or {}).get("issues") or []
        error_count = sum(1 for i in issues if i.get("severity") == "error")
        warn_count = len(issues) - error_count
        color = "#cf1322" if error_count else ("#d46b08" if warn_count else "#389e0d")
        return format_html(
            '<span style="color:{}" title="最新檢查：{}">{}({})</span>',
            color, checked_at.strftime("%Y-%m-%d %H:%M"), error_count, warn_count,
        )

    @staticmethod
    def _render_check_result(result, checked_at):
        """change page 上的檢查結果表格，兩種檢查共用。

        issue 的 source=="structure" 代表是程式算出來的結構問題（確定性），標 🔧
        跟 LLM 的判斷區分開。category 只有獨立自足性檢查會有。
        """
        result = result or {}
        issues = result.get("issues") or []
        summary = result.get("summary") or ""
        usage = result.get("usage") or {}
        model = result.get("model", "")

        rows = "".join(
            format_html(
                '<tr><td style="padding:4px 8px;white-space:nowrap;vertical-align:top">{}</td>'
                '<td style="padding:4px 8px;white-space:nowrap;vertical-align:top;color:#888">{}</td>'
                '<td style="padding:4px 8px;white-space:nowrap;vertical-align:top;color:#888">{}</td>'
                '<td style="padding:4px 8px">{}</td></tr>',
                mark_safe(
                    ("❗ error" if i.get("severity") == "error" else "⚠️ warning")
                    + (" 🔧" if i.get("source") == "structure" else "")
                ),
                i.get("category") or "",
                i.get("location") or "-",
                i.get("description", ""),
            )
            for i in issues
        )
        table = (
            format_html(
                '<table style="border-collapse:collapse;font-size:12px">{}</table>',
                mark_safe(rows),
            )
            if issues else format_html('<p style="color:#389e0d">未發現問題。</p>')
        )

        return format_html(
            '<p style="margin:0 0 6px">{}</p>'
            '<p style="color:#888;font-size:11px;margin:0 0 8px">'
            '最新檢查：{}　model：{}　'
            'token：prompt {}{} + completion {} = {}</p>'
            '{}',
            summary,
            checked_at.strftime("%Y-%m-%d %H:%M"), model,
            f'{usage.get("prompt_tokens", 0):,}',
            f'（含 cached {usage.get("cached_tokens", 0):,}）' if usage.get("cached_tokens") else "",
            f'{usage.get("completion_tokens", 0):,}',
            f'{usage.get("total_tokens", 0):,}',
            table,
        )

    @admin.display(description="Check", ordering="error_checked_at")
    def error_check_summary(self, obj):
        return self._check_summary_cell(obj.error_check_result, obj.error_checked_at)

    @admin.display(description="Self", ordering="self_checked_at")
    def self_check_summary(self, obj):
        return self._check_summary_cell(obj.self_check_result, obj.self_checked_at)

    @admin.display(description="檢查結果")
    def error_check_display(self, obj):
        if not obj.error_checked_at:
            return "尚未執行過「對照 rulebook 全文檢查流程圖」action。"
        return self._render_check_result(obj.error_check_result, obj.error_checked_at)

    @admin.display(description="檢查結果")
    def self_check_display(self, obj):
        if not obj.self_checked_at:
            return "尚未執行過「獨立檢查流程圖（不看 rulebook）」action。"
        return self._render_check_result(obj.self_check_result, obj.self_checked_at)

    @admin.display(description="React Flow JSON")
    def react_flow_json_display(self, obj):
        data = obj.adjusted_json if obj.adjusted_json else obj.react_flow_json
        if not data:
            return "—"
        pretty = json.dumps(data, ensure_ascii=False, indent=2)
        label = "adjusted_json (manual)" if obj.adjusted_json else "react_flow_json (auto-generated)"
        # Unique element ID so multiple instances on the page don't clash
        pre_id = f"rfjson_{str(obj.pk).replace('-', '_')}"
        # JavaScript handles dark-mode inline — CSS-only approaches are overridden by
        # Django admin's own stylesheets.  MutationObserver watches data-theme changes.
        script = mark_safe(
            f'<script>(function(){{'
            f'var el=document.getElementById("{pre_id}");'
            f'if(!el)return;'
            f'function a(){{'
            f'var dark=document.documentElement.getAttribute("data-theme")==="dark"'
            f'||window.matchMedia("(prefers-color-scheme:dark)").matches;'
            f'el.style.background=dark?"#1e1e1e":"#f8f8f8";'
            f'el.style.color=dark?"#eee":"#333";'
            f'el.style.borderColor=dark?"#444":"#e0e0e0";'
            f'}}'
            f'a();'
            f'new MutationObserver(a).observe('
            f'document.documentElement,{{attributes:true,attributeFilter:["data-theme"]}});'
            f'window.matchMedia("(prefers-color-scheme:dark)").addEventListener("change",a);'
            f'}})()</script>'
        )
        return format_html(
            '<p style="color:#888;font-size:11px;margin:0 0 4px">{}</p>'
            '<pre id="{}" style="background:#f8f8f8;border:1px solid #e0e0e0;color:#333;'
            'border-radius:4px;padding:12px;font-size:11px;max-height:400px;'
            'overflow:auto;white-space:pre-wrap">{}</pre>{}',
            label, pre_id, pretty, script,
        )

    @admin.display(description="Nodes", ordering="_size")
    def node_count(self, obj):
        # effective JSON（與公開頁 / check / i18n 同邏輯）——intermediate_json 只在
        # 生成當下寫入一次，編輯器存檔只動 adjusted_json，讀它會停在初版數字。
        data = obj.adjusted_json or obj.react_flow_json or {}
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        return f"{len(nodes)}n / {len(edges)}e"

    @admin.display(description="Generated")
    def generated_at_display(self, obj):
        if obj.updated_at:
            return obj.updated_at.strftime("%Y-%m-%d %H:%M")
        return "-"

    @admin.display(description="Preview")
    def preview_link(self, obj):
        url = f"/api/game/rulebooks/{obj.rulebook_id}/flowchart/?detail={obj.detail}&render=reactflow"
        return format_html(
            '<a href="{}" target="_blank" style="white-space:nowrap">🔗 Open chart</a>',
            url,
        )


@admin.register(FlowchartReview)
class FlowchartReviewAdmin(admin.ModelAdmin):
    """審核紀錄：只能看。新增一律經由 game/flowchart_review.py（審核頁、送審按鈕）。"""
    list_display = ("created_at", "flowchart_name", "action", "actor", "last_editor", "comment_short")
    list_filter = ("action",)
    search_fields = ("flowchart__rulebook__title", "flowchart__ruleset", "comment")
    list_select_related = ("flowchart__rulebook", "actor", "last_editor")
    ordering = ("-created_at",)
    exclude = ("content",)

    @admin.display(description="Flowchart", ordering="flowchart__rulebook__title")
    def flowchart_name(self, obj):
        return f"{obj.flowchart.rulebook.title} — {obj.flowchart.ruleset}"

    @admin.display(description="意見")
    def comment_short(self, obj):
        return (obj.comment[:60] + "…") if len(obj.comment) > 60 else obj.comment

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # 不能一律 False：admin 刪除流程圖／規則書時會逐一檢查 cascade 到的紀錄
        # 能不能刪，回 False 會讓 superuser 也刪不掉流程圖。
        return request.user.is_superuser


# ─────────────────────────────
# RulebookScript Admin
# ─────────────────────────────

class CopyScriptToEditionForm(forms.Form):
    target_edition = forms.ModelChoiceField(
        queryset=Edition.objects.select_related("game").all(),
        label="Target Edition",
        help_text="搜尋並選擇要連結分享的 Edition（可為不同 game）。",
    )

    def __init__(self, *args, admin_site=None, **kwargs):
        super().__init__(*args, **kwargs)
        if admin_site is not None:
            field = self.fields["target_edition"]
            field.widget = AutocompleteSelect(
                RulebookScript._meta.get_field("edition"), admin_site
            )
            # ModelChoiceField.__init__ 已把 choices 綁到「舊」widget；換 widget 後
            # 需重新指派，否則 Select.optgroups() 會拿到空 tuple 而非 ModelChoiceIterator。
            field.widget.choices = field.choices


class DuplicateScriptForm(forms.Form):
    """
    複製講稿的兩個維度：語言與 edition，各自可複選、也可留空。

    兩邊都填就取笛卡兒積（每個 edition × 每個語言各一份）；留空的那一維沿用來源
    講稿的值，所以「只換語言」與「只換 edition（規則極相似的變異版本）」都走這裡。
    """

    target_languages = forms.ModelMultipleChoiceField(
        queryset=Tribe.objects.all(),
        label="Target Languages",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="要複製成哪些語言的新草稿（把目前內容當翻譯起點）。留空＝沿用來源講稿的語言。",
    )
    target_editions = forms.ModelMultipleChoiceField(
        queryset=Edition.objects.select_related("game").all(),
        label="Target Editions",
        required=False,
        help_text="要複製到哪些 edition（例如規則極相似的變異版本）。留空＝留在來源 edition。",
    )

    def __init__(self, *args, admin_site=None, **kwargs):
        super().__init__(*args, **kwargs)
        if admin_site is not None:
            field = self.fields["target_editions"]
            field.widget = AutocompleteSelectMultiple(
                RulebookScript._meta.get_field("edition"), admin_site
            )
            # 換 widget 後要重新指派 choices，理由同 CopyScriptToEditionForm。
            field.widget.choices = field.choices

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("target_languages") and not cleaned.get("target_editions"):
            raise forms.ValidationError(
                "語言與 edition 至少要選一項，否則複製出來的會是來源講稿本身。"
            )
        return cleaned


def _script_target_rulebook(target_edition, src, language):
    """
    取得（必要時建立）target_edition 底下可掛講稿的 rulebook,回傳 (rulebook, created)。

    優先挑語言相符的那本；edition 還沒有任何 rulebook 時建一本佔位用的
    （比照 RulebookFlowchartAdmin.copy_to_edition，RulebookScript.rulebook 不可為空）。
    """
    rulebooks = target_edition.rulebooks.all()
    rulebook = rulebooks.filter(language=language).first() or rulebooks.first()
    if rulebook is not None:
        return rulebook, False

    rulebook = Rulebook.objects.create(
        edition=target_edition,
        language=target_edition.language or language or src.rulebook.language,
        title=(
            f"{target_edition.name or target_edition.game.canonical_name} — script placeholder"
        )[:200],
    )
    return rulebook, True


class RulebookScriptAdminForm(forms.ModelForm):
    """
    edition → rulebook → (ruleset, source_flowchart) 逐級收窄的表單。

    每一級的選項都由上一級決定：edition 決定有哪些 rulebook，rulebook 決定有哪些
    ruleset（取自 RulebookNode，講稿素材的唯一來源）與哪些 flowchart。前端由
    rulebook_script_form.js 走 field-options/ 即時抽換選項，這裡再做一次伺服器端
    驗證，兩邊都擋掉「選了沒有素材的 ruleset → 背景任務才失敗」這條路。
    """

    class Meta:
        model = RulebookScript
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        edition_id = self._selected("edition")
        rulebook_id = self._selected("rulebook")

        # ── rulebook：限定在所選 edition 底下 ──
        rb_field = self.fields.get("rulebook")
        if rb_field is not None:
            if edition_id or rulebook_id:
                # 既有資料的 script.edition 可能為空，仍要能顯示自己目前的 rulebook
                rb_field.queryset = Rulebook.objects.filter(
                    models.Q(edition_id=edition_id) | models.Q(pk=rulebook_id)
                ).select_related("edition")
            else:
                rb_field.queryset = Rulebook.objects.none()
            rb_field.label_from_instance = lambda obj: (
                f"{obj.title}（{obj.language.language}）" if obj.language_id else obj.title
            )
            rb_field.help_text = "先選上方的 Edition，這裡才會出現該 edition 底下的 rulebook。"
            # admin 會用 RelatedFieldWidgetWrapper 包住 Select，attrs 得設在內層才會
            # 渲染到 <select> 上（wrapper 自己的 attrs 不會往下傳）。
            widget = rb_field.widget
            inner = getattr(widget, "widget", widget)
            inner.attrs["data-options-url"] = reverse(
                "admin:game_rulebookscript_field_options"
            )

        # ── ruleset：限定在所選 rulebook 已 ingest 的 node ruleset ──
        available = node_rulesets(rulebook_id) if rulebook_id else []
        # 只有既存資料才有「目前值」；新增時的 model default 不該當成已選項目。
        # pk 是 UUIDField(default=uuid4)，未存檔也有值，只能用 _state.adding 判斷。
        current = (
            self.instance.ruleset
            if self.instance and not self.instance._state.adding
            else None
        )
        choices = list(available)
        help_text = "只列出本 rulebook 已 ingest 的 ruleset（講稿素材的來源）。"
        if not rulebook_id:
            help_text = "先選 Rulebook，這裡才會出現可用的 ruleset。"
        if current and current not in choices:
            # 保留既有的壞值以免表單無法載入，但標示出來提醒改掉
            choices = [current] + choices
            help_text = f"⚠ 目前的 '{current}' 沒有對應的 RulebookNode，生成會失敗，請改選其他值。{help_text}"
        self.fields["ruleset"] = forms.ChoiceField(
            choices=[(r, r) for r in choices],
            label="Ruleset",
            required=True,
            help_text=help_text,
        )

        # ── source_flowchart：限定在所選 rulebook 底下 ──
        fc_field = self.fields.get("source_flowchart")
        if fc_field is not None:
            fc_field.queryset = (
                RulebookFlowchart.objects.filter(rulebook_id=rulebook_id)
                if rulebook_id else RulebookFlowchart.objects.none()
            )
            # 預設 __str__ 是 "Flowchart[detailed] <uuid> (Default)"，選單裡讀不出重點；
            # 與 field_options_view 回傳的文字保持一致。
            fc_field.label_from_instance = lambda obj: f"{obj.ruleset}（{obj.detail}）"
            fc_field.label = "參考流程圖"
            fc_field.help_text = (
                "選填。指定後生成講稿時會以這張圖的節點順序核對回合流程；"
                "留空則自動找同 ruleset 的流程圖，找不到就只用規則書內文生成。"
            )

    def _selected(self, name):
        """取得目前 edition/rulebook 的值：POST 資料優先，其次是既有 instance。"""
        if self.data:
            raw = self.data.get(self.add_prefix(name))
            if raw:
                return raw
        return getattr(self.instance, f"{name}_id", None)

    def clean(self):
        cleaned = super().clean()
        rulebook = cleaned.get("rulebook")
        ruleset = cleaned.get("ruleset")
        edition = cleaned.get("edition")
        flowchart = cleaned.get("source_flowchart")

        if rulebook and edition and rulebook.edition_id != edition.id:
            self.add_error("rulebook", f"'{rulebook}' 不屬於 edition '{edition}'。")

        if rulebook and ruleset:
            available = node_rulesets(rulebook.id)
            if not available:
                self.add_error(
                    "rulebook",
                    "這本 rulebook 還沒有 whole_context，請先執行「💫1️⃣Extract by LlamaParse」。",
                )
            elif ruleset not in available:
                self.add_error(
                    "ruleset",
                    f"'{ruleset}' 不屬於這本 rulebook，可選的有：{', '.join(available)}。",
                )

        if rulebook and flowchart and flowchart.rulebook_id != rulebook.id:
            self.add_error("source_flowchart", "這張流程圖不屬於所選的 rulebook。")

        return cleaned


@admin.register(RulebookScript)
class RulebookScriptAdmin(admin.ModelAdmin):
    form = RulebookScriptAdminForm
    list_display = (
        "rulebook_title", "ruleset", "language", "title_display",
        "status", "published_display", "human_adjust", "linkage_count",
        "word_count_display", "prompt_version", "generated_at",
    )
    # is_published 刻意唯讀顯示：直接在清單勾選會跳過 publish_selected 的
    # effective_text 檢查（可能發布空講稿），且整筆覆寫會蓋掉背景生成的結果。
    # 一律走 publish_selected / unpublish_selected action。
    list_filter = ("status", "is_published", "language", "ruleset", "prompt_version", "human_adjust")
    search_fields = ("rulebook__title", "rulebook__edition__game__canonical_name", "host_persona")
    ordering = ("-updated_at",)
    # rulebook / source_flowchart 刻意不用 autocomplete：它們的選項由 edition、rulebook
    # 逐級收窄（見 RulebookScriptAdminForm），select2 的 ajax 搜尋會繞過那層限制。
    autocomplete_fields = ("edition", "language", "linked_editions")
    actions = ("generate_script", "publish_selected", "unpublish_selected", "revert_to_auto", "link_to_edition", "duplicate_script")

    class Media:
        js = ("game/admin/rulebook_script_form.js",)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "field-options/",
                self.admin_site.admin_view(self.field_options_view),
                name="game_rulebookscript_field_options",
            ),
        ]
        return custom_urls + urls

    def field_options_view(self, request):
        """供表單 JS 逐級收窄下游欄位的選項來源。"""
        edition_id = request.GET.get("edition") or None
        rulebook_id = request.GET.get("rulebook") or None
        data = {"rulebooks": [], "rulesets": [], "flowcharts": []}

        if edition_id:
            data["rulebooks"] = [
                {"id": str(rb.pk), "text": f"{rb.title}（{rb.language.language}）"
                 if rb.language_id else rb.title}
                for rb in Rulebook.objects
                .filter(edition_id=edition_id)
                .select_related("language")
                .order_by("title")
            ]

        if rulebook_id:
            data["rulesets"] = node_rulesets(rulebook_id)
            data["flowcharts"] = [
                {"id": str(fc.pk), "text": f"{fc.ruleset}（{fc.detail}）"}
                for fc in RulebookFlowchart.objects
                .filter(rulebook_id=rulebook_id)
                .order_by("ruleset")
            ]

        return JsonResponse(data)

    readonly_fields = (
        "id", "status", "title", "script_text_display",
        "source_chunk_ids", "llm_model", "prompt_version",
        "generation_error", "generated_at", "created_at", "updated_at",
    )

    fieldsets = (
        ("講稿設定（生成前填寫）", {
            "fields": ("edition", "rulebook", "ruleset", "source_flowchart",
                       "host_persona", "player_persona", "story_atmosphere", "language"),
            "description": "由上而下逐級選取：Edition → Rulebook → Ruleset / 參考流程圖。",
        }),
        ("生成結果", {
            "fields": ("status", "title", "script_text_display", "generation_error"),
        }),
        ("發布", {
            "fields": ("is_published",),
            "description": "手動勾選以對前台公開；不受重新生成或 flowchart 版本更新影響。",
        }),
        ("共用連結", {
            "fields": ("linked_editions",),
            "description": "直接讓其他 edition 共用顯示本講稿（不複製資料）。例如同一遊戲的不同語言版本共用同一份講稿；日後修改本講稿會同步反映在所有連結的 edition 上，不會各自獨立。",
        }),
        ("人工修改", {
            "fields": ("adjusted_title", "adjusted_text", "human_adjust"),
            "description": "編輯 adjusted_title / adjusted_text 修改；有值時 API 以此為準。",
        }),
        ("系統", {
            "fields": ("id", "source_chunk_ids", "llm_model", "prompt_version",
                       "generated_at", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _linked_count=models.Count("linked_editions", distinct=True)
        )

    @admin.display(description="Linked", ordering="_linked_count")
    def linkage_count(self, obj):
        return obj._linked_count or "-"

    @admin.action(description="🔗 Link to edition (share, no copy)")
    def link_to_edition(self, request, queryset):
        if "apply_link" in request.POST:
            form = CopyScriptToEditionForm(request.POST, admin_site=self.admin_site)
            if form.is_valid():
                from django.utils import timezone

                target_edition = form.cleaned_data["target_edition"]
                linked_pks = []
                for src in queryset:
                    src.linked_editions.add(target_edition)
                    linked_pks.append(src.pk)
                linked = len(linked_pks)
                # 同 RulebookFlowchart.link_to_edition：m2m add() 不碰 updated_at，
                # 不推進時間戳 delta sync 就挑不到這筆、共用關係上不了 VPS。
                if linked_pks:
                    self.model.objects.filter(pk__in=linked_pks).update(
                        updated_at=timezone.now()
                    )
                self.message_user(
                    request,
                    f"Linked {linked} script(s) to '{target_edition}' (shared, not copied).",
                    level=messages.SUCCESS,
                )
                return None
        else:
            form = CopyScriptToEditionForm(admin_site=self.admin_site)

        return TemplateResponse(
            request,
            "admin/game/rulebookscript/link_to_edition_confirm.html",
            {
                **self.admin_site.each_context(request),
                "title": "Link script(s) to edition",
                "queryset": queryset,
                "form": form,
                "opts": self.model._meta,
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
            },
        )

    @admin.action(description="⧉ Duplicate（複製到其他語言／其他 edition）")
    def duplicate_script(self, request, queryset):
        if "apply_duplicate" in request.POST:
            form = DuplicateScriptForm(request.POST, admin_site=self.admin_site)
            if form.is_valid():
                target_languages = form.cleaned_data["target_languages"]
                target_editions = form.cleaned_data["target_editions"]
                created = []
                created_rulebooks = 0

                for src in queryset:
                    if not src.effective_text:
                        self.message_user(
                            request,
                            f"⏭ '{src.rulebook.title}' 尚無內容可複製",
                            level=messages.WARNING,
                        )
                        continue

                    # 沒選的那一維＝沿用來源；None 代表「留在來源 edition」。
                    languages = list(target_languages) or [src.language]
                    editions = list(target_editions) or [None]

                    for target_edition in editions:
                        for language in languages:
                            with transaction.atomic():
                                if target_edition is None:
                                    rulebook, edition = src.rulebook, src.edition
                                else:
                                    rulebook, rb_created = _script_target_rulebook(
                                        target_edition, src, language
                                    )
                                    edition = target_edition
                                    created_rulebooks += int(rb_created)

                                where = target_edition or src.rulebook.title
                                if rulebook.id == src.rulebook_id and language.id == src.language_id:
                                    self.message_user(
                                        request,
                                        f"⏭ '{src.rulebook.title}' 已經是 {where} 的 {language} 版本",
                                        level=messages.WARNING,
                                    )
                                    continue
                                if RulebookScript.objects.filter(
                                    rulebook=rulebook, ruleset=src.ruleset, language=language,
                                ).exists():
                                    self.message_user(
                                        request,
                                        f"⏭ '{where}' 已存在 ruleset「{src.ruleset}」的 {language} 版本",
                                        level=messages.WARNING,
                                    )
                                    continue

                                created.append(RulebookScript.objects.create(
                                    rulebook=rulebook, edition=edition, ruleset=src.ruleset,
                                    language=language,
                                    host_persona=src.host_persona, player_persona=src.player_persona,
                                    story_atmosphere=src.story_atmosphere,
                                    # 流程圖綁在來源 rulebook 上，換了 rulebook 就不該沿用
                                    source_flowchart=(
                                        src.source_flowchart
                                        if rulebook.id == src.rulebook_id else None
                                    ),
                                    title=src.effective_title, script_text=src.effective_text,
                                    status=RulebookScript.Status.GENERATED,
                                ))

                if created_rulebooks:
                    self.message_user(
                        request,
                        f"ℹ 順帶建立了 {created_rulebooks} 本佔位 rulebook（目標 edition 原本沒有）。",
                        level=messages.INFO,
                    )
                if len(created) == 1:
                    self.message_user(
                        request, f"✅ Created 1 draft（{created[0].language}）.", level=messages.SUCCESS,
                    )
                    return redirect(reverse("admin:game_rulebookscript_change", args=[created[0].pk]))
                self.message_user(
                    request, f"✅ Created {len(created)} draft(s).",
                    level=messages.SUCCESS if created else messages.WARNING,
                )
                return None
        else:
            form = DuplicateScriptForm(admin_site=self.admin_site)

        return TemplateResponse(
            request,
            "admin/game/rulebookscript/duplicate_confirm.html",
            {
                **self.admin_site.each_context(request),
                "title": "Duplicate script(s)",
                "queryset": queryset,
                "form": form,
                "opts": self.model._meta,
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
            },
        )

    @admin.display(description="Rulebook")
    def rulebook_title(self, obj):
        return obj.rulebook.title

    @admin.display(description="Title")
    def title_display(self, obj):
        return obj.effective_title or "—"

    @admin.display(description="Published", ordering="is_published")
    def published_display(self, obj):
        return "✔️" if obj.is_published else "❌"

    @admin.display(description="Length")
    def word_count_display(self, obj):
        n = obj.effective_text_length
        if not n:
            return "—"
        lang_code = obj.language.language if obj.language_id else None
        unit = {"zh": "字", "ja": "拍"}.get(lang_code, "words")
        return f"{n} {unit}"

    @admin.display(description="Script Text")
    def script_text_display(self, obj):
        text = obj.effective_text
        if not text:
            return "—"
        label = "adjusted_text (manual)" if obj.adjusted_text else "script_text (auto-generated)"
        return format_html(
            '<p style="color:#888;font-size:11px;margin:0 0 4px">{}</p>'
            '<pre style="background:#f8f8f8;border:1px solid #e0e0e0;color:#333;'
            'border-radius:4px;padding:12px;font-size:11px;max-height:400px;'
            'overflow:auto;white-space:pre-wrap">{}</pre>',
            label, text,
        )

    @admin.action(description="🎙 Generate script（兼重新生成）")
    def generate_script(self, request, queryset):
        queued = skipped = failed = 0
        for obj in queryset:
            if not obj.rulebook.whole_context:
                skipped += 1
                self.message_user(
                    request,
                    f"⏭ Skipped '{obj.rulebook.title}': no whole_context "
                    f"(run 💫1️⃣Extract by LlamaParse first)",
                    level=messages.WARNING,
                )
                continue
            if not obj.host_persona and not obj.story_atmosphere:
                skipped += 1
                self.message_user(
                    request,
                    f"⏭ Skipped '{obj.rulebook.title}': host_persona 與 story_atmosphere 皆空白，請先填寫",
                    level=messages.WARNING,
                )
                continue
            available = node_rulesets(obj.rulebook_id)
            if obj.ruleset not in available:
                skipped += 1
                self.message_user(
                    request,
                    f"⏭ Skipped '{obj.rulebook.title}': ruleset '{obj.ruleset}' 沒有對應的 "
                    f"RulebookNode，請改選 {', '.join(available)}",
                    level=messages.WARNING,
                )
                continue
            try:
                obj.status = RulebookScript.Status.GENERATING
                obj.save(update_fields=["status", "updated_at"])
                async_task("game.tasks.generate_script_task", str(obj.id))
                queued += 1
            except Exception as e:
                failed += 1
                self.message_user(request, f"❌ Error queuing '{obj.rulebook.title}': {e}", level=messages.ERROR)

        self.message_user(
            request,
            f"✅ Queued {queued} script(s) for generation. Skipped {skipped}, failed {failed}.",
            level=messages.INFO if queued > 0 else messages.WARNING,
        )

    @admin.action(description="📢 Publish selected（公開）")
    def publish_selected(self, request, queryset):
        published = skipped = 0
        for obj in queryset:
            if not obj.effective_text:
                skipped += 1
                self.message_user(
                    request,
                    f"⏭ '{obj.rulebook.title}' 尚未有內容，無法發布",
                    level=messages.WARNING,
                )
                continue
            obj.is_published = True
            obj.save(update_fields=["is_published", "updated_at"])
            published += 1
        self.message_user(
            request,
            f"✅ Published {published} script(s). Skipped {skipped}.",
            level=messages.SUCCESS if published else messages.WARNING,
        )

    @admin.action(description="🚫 Unpublish selected（下架）")
    def unpublish_selected(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"Unpublished {updated} script(s).", level=messages.SUCCESS)

    @admin.action(description="↩ Revert to auto version（捨棄人工修改）")
    def revert_to_auto(self, request, queryset):
        updated = queryset.update(adjusted_title="", adjusted_text=None, human_adjust=False)
        self.message_user(request, f"Reverted {updated} script(s) to auto version.", level=messages.SUCCESS)


# ─────────────────────────────
# FlowchartTextTranslation Admin
# ─────────────────────────────

# 編輯介面：把 translations JSON 拆成各語一欄
_FC_TR_LANGS = [
    ("en", "English (en)"),
    ("zh", "華文 (zh)"),
    ("ja", "日本語 (ja)"),
    ("fr", "Français (fr)"),
    ("de", "Deutsch (de)"),
    ("es", "Español (es)"),
]


def _fc_tr_field(label):
    return forms.CharField(
        label=label, required=False,
        widget=forms.Textarea(attrs={"rows": 2, "style": "width:60%;"}),
    )


class FlowchartTextTranslationForm(forms.ModelForm):
    # 類別層級宣告各語欄位（admin get_form 會先驗證 fields，必須在此可見）
    t_en = _fc_tr_field("English (en)")
    t_zh = _fc_tr_field("華文 (zh)")
    t_ja = _fc_tr_field("日本語 (ja)")
    t_fr = _fc_tr_field("Français (fr)")
    t_de = _fc_tr_field("Deutsch (de)")
    t_es = _fc_tr_field("Español (es)")

    class Meta:
        model = FlowchartTextTranslation
        fields = []  # model 欄位全由上面的各語自訂欄位處理（is_manual 不在表單上顯示）

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tr = (getattr(self.instance, "translations", None) or {})
        for code, _label in _FC_TR_LANGS:
            self.fields["t_" + code].initial = tr.get(code, "")

    def save(self, commit=True):
        obj = super().save(commit=False)
        tr = dict(getattr(obj, "translations", None) or {})
        for code, _ in _FC_TR_LANGS:
            val = (self.cleaned_data.get("t_" + code) or "").strip()
            if val:
                tr[code] = val
            else:
                tr.pop(code, None)
        obj.translations = tr
        if commit:
            obj.save()
        return obj


class FlowchartTextCompletenessFilter(admin.SimpleListFilter):
    """翻譯完整度。不存欄位，直接看 translations 這個 JSON 有沒有各語言的 key。"""
    title = "翻譯完整度"
    parameter_name = "completeness"

    def lookups(self, request, model_admin):
        from game.rag.flowchart.i18n import LANGS
        return [("complete", "六語齊全"), ("incomplete", "缺任一語言")] + [
            (f"missing_{code}", f"缺 {code}") for code in LANGS
        ]

    def queryset(self, request, queryset):
        from game.rag.flowchart.i18n import LANGS

        value = self.value()
        if value == "complete":
            return queryset.filter(translations__has_keys=LANGS)
        if value == "incomplete":
            return queryset.exclude(translations__has_keys=LANGS)
        if value and value.startswith("missing_") and value[8:] in LANGS:
            return queryset.exclude(translations__has_key=value[8:])
        return queryset


def _chart_text_hashes(charts):
    from game.rag.flowchart.i18n import _norm_lang, chart_text_sources

    hashes = set()
    for chart in charts:
        rb = chart.rulebook
        src = _norm_lang(rb.language.language if rb.language_id else "en")
        hashes.update(chart_text_sources(chart.effective_json, chart.ruleset, src))
    return hashes


class FlowchartTextChartFilter(admin.SimpleListFilter):
    """?chart=<flowchart_id>：只顯示這張流程圖（草稿）用到的文字。網址即範圍。"""
    title = "所屬流程圖"
    parameter_name = "chart"

    def lookups(self, request, model_admin):
        value = request.GET.get(self.parameter_name)
        if not value:
            return []
        chart = RulebookFlowchart.objects.filter(pk=value).select_related("rulebook").first() \
            if _is_uuid(value) else None
        return [(value, f"{chart.rulebook.title} — {chart.ruleset}" if chart else value)]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        if not _is_uuid(value):
            return queryset.none()
        charts = RulebookFlowchart.objects.filter(pk=value).select_related("rulebook__language")
        return queryset.filter(text_hash__in=_chart_text_hashes(charts))


class FlowchartTextRulebookFilter(admin.SimpleListFilter):
    """?rulebook=<rulebook_id>：只顯示這本 rulebook 底下所有流程圖用到的文字。"""
    title = "所屬 Rulebook"
    parameter_name = "rulebook"

    def lookups(self, request, model_admin):
        value = request.GET.get(self.parameter_name)
        if not value:
            return []
        rb = Rulebook.objects.filter(pk=value).first() if _is_uuid(value) else None
        return [(value, rb.title if rb else value)]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        if not _is_uuid(value):
            return queryset.none()
        charts = RulebookFlowchart.objects.filter(rulebook_id=value).select_related("rulebook__language")
        return queryset.filter(text_hash__in=_chart_text_hashes(charts))


def _is_uuid(value):
    import uuid as _uuid
    try:
        _uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


@admin.register(FlowchartTextTranslation)
class FlowchartTextTranslationAdmin(admin.ModelAdmin):
    """flowchart 文字的多語翻譯快取，可手動修正過長／不精準的譯文（各語一欄）。"""

    form = FlowchartTextTranslationForm
    # is_manual 欄位刻意不在列表、篩選與表單上顯示（強制重譯／補譯缺漏準備淘汰，
    # 這個鎖不再需要人工操作）。model 欄位與 save_model 的自動上鎖保留，免得為此 migrate。
    list_display = ("source_text_short", "source_lang", "flowchart_usage_count", "updated_at")
    list_filter = (
        "source_lang", FlowchartTextCompletenessFilter,
        FlowchartTextChartFilter, FlowchartTextRulebookFilter,
    )
    change_list_template = "admin/game/flowcharttexttranslation/change_list.html"
    search_fields = ("source_text",)
    ordering = ("-updated_at",)
    readonly_fields = (
        "text_hash", "source_text", "source_lang",
        "created_at", "updated_at", "used_by_flowcharts_display",
    )
    fields = (
        "source_text", "source_lang",
        "t_de", "t_en", "t_es", "t_fr", "t_ja", "t_zh", 
        "text_hash", "used_by_flowcharts_display",
        "created_at", "updated_at",
    )
    actions =("gc_unused", "release_manual_lock", "force_retranslate")

    # ── 按流程圖批次翻譯 ─────────────────────────────────────────────
    # 網址就是範圍：translate/<chart_id>/ 永遠只處理那一張圖的草稿文字。
    # 只要求 change_flowcharttexttranslation，不要求流程圖本身的權限（翻譯員群組沒有）。

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("translate/", self.admin_site.admin_view(self.translate_picker_view),
                 name="game_flowcharttexttranslation_translate"),
            path("translate/<uuid:chart_id>/", self.admin_site.admin_view(self.translate_batch_view),
                 name="game_flowcharttexttranslation_translate_chart"),
        ]
        return custom + urls

    def _chart_qs(self):
        return RulebookFlowchart.objects.select_related(
            "rulebook__language", "rulebook__edition__game",
        )

    def translate_picker_view(self, request):
        from django.core.exceptions import PermissionDenied
        from game.rag.flowchart.i18n import pending_counts

        if not self.has_change_permission(request):
            raise PermissionDenied
        charts = self._chart_qs()
        rulebook_id = request.GET.get("rulebook")
        if rulebook_id:
            charts = charts.filter(rulebook_id=rulebook_id) if _is_uuid(rulebook_id) else charts.none()
        charts = list(charts)
        counts = pending_counts(charts)
        show_all = request.GET.get("all") == "1"
        rows = [
            {"chart": c, "pending": counts[c.pk],
             "url": reverse("admin:game_flowcharttexttranslation_translate_chart", args=[c.pk])}
            for c in charts if show_all or counts[c.pk]
        ]
        rows.sort(key=lambda r: (-r["pending"], r["chart"].rulebook.title, r["chart"].ruleset))
        return TemplateResponse(request, "admin/game/flowcharttexttranslation/translate_picker.html", {
            **self.admin_site.each_context(request),
            "title": "按流程圖批次翻譯",
            "opts": self.model._meta,
            "rows": rows,
            "show_all": show_all,
            "rulebook_id": rulebook_id or "",
        })

    def translate_batch_view(self, request, chart_id):
        from django.core.exceptions import PermissionDenied
        from django.shortcuts import get_object_or_404
        from django.utils import timezone
        from game.rag.flowchart.i18n import LANGS, chart_text_sources, pending_translations

        if not self.has_change_permission(request):
            raise PermissionDenied
        chart = get_object_or_404(self._chart_qs(), pk=chart_id)
        only_lang = request.GET.get("lang") if request.GET.get("lang") in LANGS else None
        back_url = reverse("admin:game_flowcharttexttranslation_translate_chart", args=[chart.pk])
        if only_lang:
            back_url += f"?lang={only_lang}"

        if request.method == "POST":
            # 只接受這張圖現在用到的文字：不能憑 POST 寫入任意 hash
            all_items = chart_text_sources(
                chart.effective_json, chart.ruleset, self._chart_src(chart),
            )
            written = created = 0
            with transaction.atomic():
                rows = {
                    r.text_hash: r
                    for r in FlowchartTextTranslation.objects.select_for_update().filter(
                        text_hash__in=list(all_items)
                    )
                }
                new_rows, changed_rows = [], []
                now = timezone.now()
                for h, item in all_items.items():
                    values = {}
                    for lang in LANGS:
                        val = (request.POST.get(f"t__{h}__{lang}") or "").strip()
                        if val:
                            values[lang] = val
                    row = rows.get(h)
                    src = row.source_lang if row else item["source_lang"]
                    # 來源語言那格不接受改寫：它就是原文
                    values.pop(src, None)
                    if row is None:
                        if not values:
                            continue
                        new_rows.append(FlowchartTextTranslation(
                            text_hash=h, source_text=item["text"], source_lang=src,
                            translations={src: item["text"], **values}, is_manual=True,
                        ))
                        continue
                    tr = dict(row.translations or {})
                    diff = {k: v for k, v in values.items() if tr.get(k) != v}
                    if not diff:
                        continue
                    tr.update(diff)
                    row.translations = tr
                    row.is_manual = True
                    row.updated_at = now
                    changed_rows.append(row)
                if new_rows:
                    FlowchartTextTranslation.objects.bulk_create(new_rows, ignore_conflicts=True)
                if changed_rows:
                    FlowchartTextTranslation.objects.bulk_update(
                        changed_rows, ["translations", "is_manual", "updated_at"]
                    )
                created, written = len(new_rows), len(changed_rows)
            remaining = len(pending_translations([chart])[chart.pk])
            self.message_user(
                request,
                f"已儲存：更新 {written} 段、新增 {created} 段。這張圖還剩 {remaining} 段待翻譯。",
                level=messages.SUCCESS,
            )
            return redirect(back_url)

        pending = pending_translations([chart], only_lang=only_lang)[chart.pk]
        label = dict(_FC_TR_LANGS)
        items = []
        for item in pending:
            items.append({
                "hash": item.text_hash,
                "text": item.source_text,
                "source_lang": item.source_lang,
                "usages": item.usages,
                "has_row": item.has_row,
                "fields": [
                    {
                        "lang": lang,
                        "label": label[lang],
                        "name": f"t__{item.text_hash}__{lang}",
                        "value": item.current.get(lang, ""),
                        "missing": lang in item.missing,
                    }
                    for lang in LANGS if lang != item.source_lang
                ],
            })
        total_texts = len(chart_text_sources(
            chart.effective_json, chart.ruleset, self._chart_src(chart),
        ))
        rb = chart.rulebook
        edition = rb.edition
        return TemplateResponse(request, "admin/game/flowcharttexttranslation/translate_batch.html", {
            **self.admin_site.each_context(request),
            "title": f"批次翻譯：{rb.title}（{chart.ruleset}）",
            "opts": self.model._meta,
            "chart": chart,
            "rulebook": rb,
            "edition": edition,
            "game_name": (edition.name or edition.game.canonical_name) if edition else "",
            "rulebook_lang": rb.language.language if rb.language_id else "en",
            "items": items,
            "total_texts": total_texts,
            "pending_count": len(items),
            "only_lang": only_lang or "",
            "langs": [(c, label[c]) for c in LANGS],
            "picker_url": reverse("admin:game_flowcharttexttranslation_translate"),
        })

    @staticmethod
    def _chart_src(chart):
        from game.rag.flowchart.i18n import _norm_lang
        rb = chart.rulebook
        return _norm_lang(rb.language.language if rb.language_id else "en")

    @admin.action(description="🎯強制重新翻譯所選項目")
    def force_retranslate(self, request, queryset):
        from game.rag.flowchart.i18n import _get_backends, _translate_texts, LANGS

        backends = _get_backends()
        if not backends:
            self.message_user(request, "❌ 未設定任何翻譯後端（DEEPL_AUTH_KEY），無法翻譯。", level=messages.ERROR)
            return

        # 依來源語言分組，以便批次翻譯
        from collections import defaultdict
        grouped = defaultdict(list)
        for obj in queryset:
            grouped[obj.source_lang].append(obj)

        success_count = 0
        fail_count = 0
        partial_langs = set()

        for src_lang, objs in grouped.items():
            texts = [obj.source_text for obj in objs]
            translations_by_text = {t: {src_lang: t} for t in texts}

            for lang in LANGS:
                if lang == src_lang:
                    continue
                try:
                    out_map = _translate_texts(texts, src_lang, lang, backends)
                    for text, val in out_map.items():
                        translations_by_text[text][lang] = val
                    if len(out_map) < len(texts):
                        # 部分未譯：這一列仍會被算成功（其他語言有譯出），
                        # 若不另外記錄就完全看不出來少了哪一語。
                        partial_langs.add(lang)
                except Exception:
                    logger.exception("強制翻譯失敗（從 %s 到 %s）", src_lang, lang)
                    partial_langs.add(lang)

            # 更新回資料庫
            for obj in objs:
                t = obj.source_text
                # 如果有成功翻譯到任何其他語言
                if len(translations_by_text[t]) > 1:
                    obj.translations = translations_by_text[t]
                    obj.is_manual = False
                    obj.save(update_fields=["translations", "is_manual", "updated_at"])
                    success_count += 1
                else:
                    fail_count += 1

        if not fail_count and not partial_langs:
            self.message_user(
                request, f"強制重譯完成：成功 {success_count} 筆。", level=messages.SUCCESS
            )
            return

        msg = f"⚠️ 強制重譯：成功 {success_count} 筆，失敗 {fail_count} 筆。"
        if partial_langs:
            msg += f"部分語言未譯完（{'/'.join(sorted(partial_langs))}），詳見 log。"
        self.message_user(request, msg, level=messages.ERROR)

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # 「使用數」只顯示在列表頁；編輯頁與其他呼叫不必每次掃全部圖表
        match = getattr(request, "resolver_match", None)
        if not (match and match.url_name and match.url_name.endswith("_changelist")):
            return qs
        # 預先計算 text_hash -> 使用此譯文的 flowchart 數量，避免 list 每列重複掃描
        # 需與 collect_inuse_hashes() 的判斷邏輯一致（node 文字 + ruleset 名稱），
        # 否則會出現「使用數 0」但 GC 因 ruleset 引用而不刪除的不一致畫面。
        from game.rag.flowchart.i18n import chart_inuse_jsons, collect_texts, compute_hash, inuse_charts
        counts: dict = {}
        for chart in inuse_charts():
            # 草稿與公開版的文字合併後才計數，一張圖對同一段文字只算一次
            chart_hashes = {
                compute_hash(text)
                for data in chart_inuse_jsons(chart)
                for text in collect_texts(data)
            }
            if chart.ruleset:
                chart_hashes.add(compute_hash(chart.ruleset))
            for h in chart_hashes:
                counts[h] = counts.get(h, 0) + 1
        self._hash_to_count = counts
        return qs

    def save_model(self, request, obj, form, change):
        # 人工在 admin 改了任一語欄 → 鎖定，之後強制重譯不會覆蓋
        lang_fields = ["t_" + c for c, _ in _FC_TR_LANGS]
        if change and any(f in form.changed_data for f in lang_fields):
            obj.is_manual = True
        super().save_model(request, obj, form, change)

    @admin.display(description="Source text", ordering="source_text")
    def source_text_short(self, obj):
        return (obj.source_text[:60] + "…") if len(obj.source_text) > 60 else obj.source_text

    @admin.display(description="使用數")
    def flowchart_usage_count(self, obj):
        return getattr(self, "_hash_to_count", {}).get(obj.text_hash, 0)

    @admin.display(description="使用此譯文的 Flowcharts")
    def used_by_flowcharts_display(self, obj):
        from game.rag.flowchart.i18n import chart_inuse_jsons, collect_texts, compute_hash, inuse_charts

        if not obj or not obj.text_hash:
            return "—"

        target_hash = obj.text_hash
        items = []
        # 原本 select_related("rulebook") 不限欄位，會把每本規則書全文一起載入
        for chart in inuse_charts(with_rulebook_title=True):
            matched = any(
                compute_hash(text) == target_hash
                for data in chart_inuse_jsons(chart)
                for text in collect_texts(data)
            )
            if not matched and chart.ruleset and compute_hash(chart.ruleset) == target_hash:
                matched = True
            if matched:
                url = reverse("admin:game_rulebookflowchart_change", args=[chart.pk])
                title = chart.rulebook.title if chart.rulebook_id else f"Flowchart {chart.pk}"
                label = f"{title} — {chart.ruleset or '(no ruleset)'}"
                items.append(format_html('<li><a href="{}">{}</a></li>', url, label))
        if not items:
            return "—"
        return format_html(
            '<ul style="margin:0;padding-left:20px;">{}</ul>',
            mark_safe("".join(items)),
        )

    @admin.action(description="取消手動鎖定（之後重譯會以機器翻譯覆蓋）")
    def release_manual_lock(self, request, queryset):
        n = queryset.update(is_manual=False)
        self.message_user(request, f"已取消 {n} 筆的手動鎖定。", level=messages.SUCCESS)

    @admin.action(
        description="🧹清除未使用的譯文（GC：刪除沒有任何圖表引用的 row；全域，忽略勾選）",
        permissions=["delete"],
    )
    def gc_unused(self, request, queryset):
        from game.rag.flowchart.i18n import gc_translations
        res = gc_translations(dry_run=False)
        self.message_user(
            request,
            f"GC 完成：總計 {res['total']} 筆，在用 {res['in_use']} 段，刪除孤兒 {res['deleted']} 筆。",
            level=messages.SUCCESS,
        )


