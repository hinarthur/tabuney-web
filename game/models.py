
import uuid, hashlib, os, math, re
from django.db import models
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator

from translation.models import Tribe, Region
from .utils import edition_thumbnail_upload


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

# 每個實體產品（基本版、擴充、變體）都是獨立的 Game entry，與 BGG 模式對齊
# Game (每個實體產品)
#   ├── GameTitle (多語言標題)
#   └── Edition (版本特定資訊：語言 / 出版社 / 地區)
#       └── Rulebook
#           ├── RulebookNode (Hierarchical Tree)
#           └── RulebookQA

ENTITY_TYPE_CHOICES = (
    ('individual', '個人'),
    ('company', '公司'),
    ('team', '團隊'),
)

EDITION_ROLE_CHOICES = (
    ('publisher', 'publisher'),
    ('designer', 'designer'),
    ('artist', 'artist'),
)

COMPONENT_MATERIAL_CHOICES = (
    ('paper',     'Paper Components'),
    ('plastic',   'Plastic'),
    ('wood',      'Wood'),
    ('metal',     'Metal'),
    ('composite', 'Composite'),
    ('fabric',    'Fabric'),
)

COMPONENT_TYPE_CHOICES = (
    ('bag',       'Bag'),
    ('board',     'Board'),
    ('card',      'Card'),
    ('chip',      'Chip'),
    ('cube',      'Cube'),
    ('die',       'Die'),
    ('meeple',    'Meeple'),
    ('miniature', 'Miniature'),
    ('tile',      'Tile'),
    ('token',     'Token'),
    ('booklet',   'Booklet / Rulebook'),
    ('other',     'Other'),
)

READING_DENSITY_CHOICES = (
    ('none',    'None'),
    ('labels',  'Labels'),
    ('simple',  'Simple'),
    ('complex', 'Complex'),
)

class Entity(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    entity_type = models.CharField(max_length=50, default='company', choices=ENTITY_TYPE_CHOICES)
    website = models.URLField(blank=True, null=True)
    
    scraper_name = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="game/scrapers/ 下的 python 檔名（不含 .py），例如 bgg_scraper"
    )
    last_scraped_at = models.DateTimeField(
        null=True, blank=True,
        help_text="最近一次成功執行爬蟲的時間"
    )
    scraper_cookie = models.TextField(
        blank=True, null=True,
        help_text=(
            "若目標網站有 Cloudflare 保護，請在瀏覽器訪問網站後，"
            "從 DevTools (F12 → Network → 任一 Request → Headers → Cookie) "
            "複製完整 Cookie 字串貼在這裡。"
        )
    )
    scraper_user_agent = models.TextField(
        blank=True, null=True,
        help_text=(
            "Cloudflare 會檢查 Cookie 與 User-Agent 是否匹配。"
            "請在這裡貼上你瀏覽器的 User-Agent (F12 → Console 輸入 navigator.userAgent)"
        )
    )
    scrape_page_start = models.IntegerField(
        default=1,
        verbose_name="起始頁",
        help_text="從第幾頁開始爬",
    )
    scrape_batch_size = models.IntegerField(
        default=0,
        verbose_name="每次頁數",
        help_text="每次爬幾頁",
    )

    def __str__(self):
        return self.name

class Game(TimeStampedModel):
    """
    每個實體產品（基本版、擴充、變體…）都是獨立的 Game entry，與 BGG 模式對齊。
    擴充/變體透過 parent_game FK 指向依賴的主 Game。
    """
    class Kind(models.TextChoices):
        STANDALONE = "standalone", "Standalone"
        EXPANSION  = "expansion",  "Expansion"
        VARIANT    = "variant",    "Variant"
        BUNDLE     = "bundle",     "Bundle"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    canonical_name = models.CharField(max_length=200)   # 內部主要名稱
    bgg_id = models.IntegerField(null=True, blank=True, unique=True)

    kind = models.CharField(
        max_length=20, choices=Kind.choices,
        null=True, blank=True,
        help_text="產品類型：基本版 / 擴充 / 變體 / 套裝"
    )
    min_players = models.PositiveSmallIntegerField(null=True, blank=True)
    max_players = models.PositiveSmallIntegerField(null=True, blank=True)
    min_playtime = models.PositiveSmallIntegerField(null=True, blank=True, help_text="minutes")
    max_playtime = models.PositiveSmallIntegerField(null=True, blank=True, help_text="minutes")

    parent_game = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='children',
        help_text="擴充/變體指向依賴的主 Game"
    )

    affiliate = models.ForeignKey(
        'ad.Affiliate',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="games"
    )
    
    # BGG data
    bgg_category = models.JSONField(
        null=True, blank=True,
        help_text="BoardGameGeek categories"
    )
    bgg_mechanism = models.JSONField(
        null=True, blank=True,
        help_text="BoardGameGeek mechanisms"
    )
    
    # Educational skill ratings (0-5 scale)
    adaptability = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Adaptability skill rating (0-5)"
    )
    collaboration = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Collaboration skill rating (0-5)"
    )
    communication = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Communication skill rating (0-5)"
    )
    creativity = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Creativity skill rating (0-5)"
    )
    critical_thinking = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Critical thinking skill rating (0-5)"
    )
    problem_solving = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Problem solving skill rating (0-5)"
    )

    # Cached composite score derived from the 6 PLATVM ratings above (RMS distance from a
    # perfect 5 on each axis, inverted). Stored (rather than computed per-request) so the
    # game search page can `order_by("-cq")` cheaply; recalculated automatically on save().
    cq = models.FloatField(
        null=True, blank=True, editable=False, db_index=True,
        help_text="Composite quality score computed from the PLATVM ratings"
    )

    # Physical/ability tags
    sensory = models.BooleanField(default=False, help_text="Requires sensory processing (visual/auditory/tactile)")
    dexterity = models.BooleanField(default=False, help_text="Requires fine motor skills or dexterity")
    spatial = models.BooleanField(default=False, help_text="Requires spatial reasoning or manipulation")

    # Reading density
    reading_density = models.CharField(
        max_length=20,
        choices=READING_DENSITY_CHOICES,
        null=True, blank=True,
        help_text="Reading density in the game components（不計cue cards或rulebook）"
    )

    class Meta:
        indexes = [models.Index(fields=["canonical_name"])]

    PLATVM_FIELDS = (
        "problem_solving", "collaboration", "adaptability",
        "critical_thinking", "communication", "creativity",
    )

    def compute_cq(self):
        """5 - SQRT(SUMSQ(5 - each PLATVM rating) / 6); missing ratings count as 0."""
        values = [getattr(self, field) or 0 for field in self.PLATVM_FIELDS]
        sumsq = sum((5 - v) ** 2 for v in values)
        return 5 - math.sqrt(sumsq / len(values))

    def save(self, *args, **kwargs):
        self.cq = self.compute_cq()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.canonical_name


class Dimension(TimeStampedModel):
    """
    Educational skill dimensions for a game - stored as JSON for flexibility.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="dimensions")

    # 7 educational skill JSON fields
    adaptability = models.JSONField(null=True, blank=True, help_text="Adaptability skill data")
    collaboration = models.JSONField(null=True, blank=True, help_text="Collaboration skill data")
    communication = models.JSONField(null=True, blank=True, help_text="Communication skill data")
    creativity = models.JSONField(null=True, blank=True, help_text="Creativity skill data")
    critical_thinking = models.JSONField(null=True, blank=True, help_text="Critical thinking skill data")
    problem_solving = models.JSONField(null=True, blank=True, help_text="Problem solving skill data")
    basic = models.JSONField(null=True, blank=True, help_text="Basic skill data")

    # Source information
    source_member = models.ForeignKey(
        'member.Member',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dimensions",
        default=3,
        help_text="Member who provided the dimension data"
    )

    class Meta:
        verbose_name = "Dimension"
        verbose_name_plural = "Dimensions"
        constraints = [
            models.UniqueConstraint(
                fields=["game"],
                name="uq_dimension_game",
            )
        ]

    def __str__(self):
        return f"Dimensions for {self.game.canonical_name}"


class GameTitle(TimeStampedModel):
    """
    多語 / 別名；讓搜尋與顯示更友善
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="titles")

    # 原本 language_code -> language (FK to Tribe)
    language = models.ForeignKey(
        Tribe, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="game_titles"
    )

    title = models.CharField(max_length=200)
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["game", "language", "title"],
                name="uq_game_language_title"
            )
        ]
        indexes = [
            models.Index(fields=["language", "title"]),
        ]

    def __str__(self):
        lang = self.language.language if self.language else "n/a"
        return f"{self.title} ({lang})"


class Edition(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    game = models.ForeignKey("Game", on_delete=models.CASCADE, related_name="editions")

    # 這個 Edition 的「主要/預設語言」（可空：因為可能同盒附多語 rulebook）
    language = models.ForeignKey(
        Tribe, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="editions"
    )

    # 包裝上出現的語言集合（可選填）
    packaging_languages = models.ManyToManyField(
        Tribe, blank=True, related_name="editions_packaging"
    )

    # # 市場/地區（不確定就 GLOBAL）
    region = models.ForeignKey(
        Region,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="editions",
    )

    # 條碼（不確定可空；若填了建議唯一, 用constraint監控uniqueness）
    barcode = models.CharField(max_length=64, null=True, blank=True)

    # 版本標籤（例如：繁中首刷 / 2nd Edition / Bilingual Packaging）
    name = models.CharField(max_length=200, blank=True)
    release_year = models.PositiveIntegerField(null=True, blank=True)

    # SEO 網址。null 是刻意的：繞過 save() 的建立路徑（例如 sync 的 raw save）
    # 會退化成 UUID 網址而不是讓頁面 500。Postgres 視 NULL 互不相等，故可與 unique 並存。
    slug = models.SlugField(
        max_length=220, unique=True, null=True, blank=True,
        db_index=True, allow_unicode=True,
        help_text="SEO 網址，例如 /games/catan-2nd-edition-2019/。留空會在儲存時自動產生。",
    )

    # 你決定一律放 Edition 的資訊（避免 override）
    thumbnail = models.ImageField(upload_to=edition_thumbnail_upload, blank=True)
    thumbnail_optimized = models.BooleanField(default=False, help_text="Thumbnail has been background-removed")
    summary = models.TextField(blank=True)
    
    age = models.PositiveSmallIntegerField(null=True, blank=True)    # 建議年齡（盒上標示）

    # 色覺友善：元件不依賴單一顏色線索（色盲／色弱可辨識）。
    # 三態：None = 尚未確認、True = 確認友善、False = 確認不友善。只有 True 會在前台顯示 icon。
    color_vision_friendly = models.BooleanField(
        null=True, blank=True, default=None,
        help_text="色覺友善（色盲/色弱可辨識）。留空 = 尚未確認",
    )

    # min_players = models.PositiveSmallIntegerField(null=True, blank=True)
    # max_players = models.PositiveSmallIntegerField(null=True, blank=True)
    # min_playtime = models.PositiveSmallIntegerField(null=True, blank=True)     # minutes
    # max_playtime = models.PositiveSmallIntegerField(null=True, blank=True)     # minutes

    is_primary = models.BooleanField(default=False)

    # 翻譯/改編版基於哪個 edition（可用於 fallback、來源標示）
    based_on = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="derived_editions"
    )

    # created_at = models.DateTimeField(auto_now_add=True)
    # updated_at = models.DateTimeField(auto_now=True)
    
    msrp = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        verbose_name="MSRP",
        help_text="Manufacturer's Suggested Retail Price"
    )
    msrp_currency = models.ForeignKey(
        'commerce.Currency',  # 注意這裡用字串引用
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="editions_msrp"
    )
    view_count = models.PositiveIntegerField(default=0)

    # 三個 role property 都走 self.roles.all() 而非 .filter()，才能共用
    # EditionDetailView 的 prefetch_related('roles__entity')，不然每個都各發一次查詢。
    @property
    def publisher_entities(self):
        return [r.entity for r in self.roles.all() if r.role == 'publisher']

    @property
    def designer_entities(self):
        return [r.entity for r in self.roles.all() if r.role == 'designer']

    @property
    def artist_entities(self):
        return [r.entity for r in self.roles.all() if r.role == 'artist']

    class Meta:
        permissions = [
            ("import_edition", "Can use the 版本輸入 (edition import) page"),
        ]
        indexes = [
            models.Index(fields=["game", "language"]),
            models.Index(fields=["game", "is_primary"]),
            models.Index(fields=["region"]),
            models.Index(fields=["barcode"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "name", "release_year"],
                name="uq_edition_game_name_release_year",
            ),
            models.UniqueConstraint(
                fields=["barcode"],
                condition=Q(barcode__isnull=False),
                name="uq_edition_barcode_not_null",
            ),
        ]

    def __str__(self):
        lang = self.language.language if self.language else "n/a"
        if self.pk:
            pubs = ", ".join([r.entity.name for r in self.roles.filter(role='publisher')])
            pub_display = pubs if pubs else "Unknown Publisher"
        else:
            pub_display = "Unknown Publisher"
        return f"{self.game} / {pub_display} [{lang}] {self.name}".strip()
    
    def get_price_display(self):
        """格式化價格顯示"""
        if self.msrp and self.msrp_currency:
            return f"{self.msrp_currency.symbol}{self.msrp}"
        return "Price not available"
    
    def get_absolute_url(self):
        # `or str(self.pk)` 是必要的：少了它，一個 null slug 會渲染出 /games/None/
        # 並讓整個搜尋列表 500。網址路由同時接受 slug 與裸 UUID。
        from django.urls import reverse
        return reverse("games:edition-detail", kwargs={"slug": self.slug or str(self.pk)})

    def save(self, *args, **kwargs):
        """
        Handle thumbnail changes for gamesync without interfering with file upload.
        """
        if not self.slug:
            from game.slugs import build_unique_edition_slug
            self.slug = build_unique_edition_slug(self)
            # 若呼叫端限定了 update_fields，得把 slug 補進去否則不會被寫入
            update_fields = kwargs.get("update_fields")
            if update_fields is not None and "slug" not in update_fields:
                kwargs["update_fields"] = list(update_fields) + ["slug"]

        # Check if this is an existing instance
        if self.pk:
            try:
                old_instance = Edition.objects.get(pk=self.pk)
                # If thumbnail is changing
                if old_instance.thumbnail and old_instance.thumbnail != self.thumbnail:
                    # Delete the old file if it exists
                    if os.path.isfile(old_instance.thumbnail.path):
                        try:
                            os.remove(old_instance.thumbnail.path)
                        except Exception:
                            # Log error or ignore if file couldn't be deleted
                            pass
                    
                    # mark it for gamesync
                    self._refresh_updated_at = True
                elif not old_instance.thumbnail and self.thumbnail:
                    self._refresh_updated_at = True
                    
            except Edition.DoesNotExist:
                pass

        # Call parent save normally
        super().save(*args, **kwargs)

        # If thumbnail changed and we need to refresh updated_at
        if hasattr(self, '_refresh_updated_at'):
            # Update only the updated_at field
            Edition.objects.filter(pk=self.pk).update(updated_at=timezone.now())
            delattr(self, '_refresh_updated_at')


class EditionSlugAlias(TimeStampedModel):
    """
    Edition 改名後留下的舊 slug，用來發 301 而不是 404。

    只由 EditionAdmin 的「重新產生 SEO 網址」action 寫入 —— slug 不會隨改名自動重算，
    因為線上網址必須穩定，編輯改個錯字不該無聲斷掉外部連結。

    UUID pk 是刻意的：本地與 VPS 是兩個獨立資料庫，autoincrement pk 遲早跨庫撞號。
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name="slug_aliases")
    slug = models.SlugField(max_length=220, unique=True, db_index=True, allow_unicode=True)

    class Meta:
        verbose_name = "Edition 舊網址"
        verbose_name_plural = "Edition 舊網址"

    def __str__(self):
        return f"{self.slug} → {self.edition_id}"


class EditionRole(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name='roles')
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name='edition_roles')
    role = models.CharField(max_length=50, default='publisher')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["edition", "entity", "role"], name="uq_edition_entity_role")
        ]

    def __str__(self):
        return f"{self.edition.name} - {self.entity.name} ({self.role})"


def rulebook_file_path(instance, filename):
    """
    生成 Rulebook PDF 儲存路徑（以 UUID 前綴分層）：
    rulebooks/<uuid[:2]>/<uuid[2:4]>/<uuid>.pdf
    """
    rb_id = getattr(instance, "id", None) or uuid.uuid4()
    rb_hex = rb_id.hex  # 32 chars, no hyphens
    p1, p2 = rb_hex[:2], rb_hex[2:4]
    return f"rulebooks/{p1}/{p2}/{rb_id}.pdf"

class RulebookStatus(models.TextChoices):
    PENDING   = "pending",   "Pending"
    PARSED    = "parsed",    "Parsed"
    VALIDATED = "validated", "Validated"
    INDEXED   = "indexed",   "Indexed"
    FAILED    = "failed",    "Failed"

class Rulebook(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name="rulebooks")

    # 每份 rulebook 自己帶語言：支援同一 edition 多語規則書
    language = models.ForeignKey(
        Tribe, on_delete=models.PROTECT, related_name="rulebooks"
    )
    
    title = models.CharField(max_length=200, default="Rulebook")
    source_url = models.URLField(blank=True)
    # 由 check_rulebook_source_urls 定期更新。unknown＝沒檢查過，或對方擋機器人
    # （403/429 等），不能算壞；只有 404/410/DNS 失敗等才會連續累計到 broken。
    source_url_status = models.CharField(
        max_length=10,
        choices=[("unknown", "Unknown"), ("ok", "OK"), ("broken", "Broken")],
        default="unknown",
    )
    source_url_fail_count = models.PositiveSmallIntegerField(default=0)
    source_url_checked_at = models.DateTimeField(null=True, blank=True)
    file = models.FileField(upload_to=rulebook_file_path, blank=True)

    # LlamaParse 擷取的原稿：每次擷取都覆寫。全站只寫不讀（chunking 讀 processed_text，
    # 問答讀 whole_context），純粹留底 —— 要把新原稿正式啟用，在 admin 編輯頁
    # 手動複製貼上到 whole_context。
    extracted_text = models.TextField(blank=True)
    
    # 人工修正後的文字（用於 chunking 和 embedding）
    processed_text = models.TextField(
        blank=True,
        help_text="人工修正後的文本，用於 chunking 和 embedding"
    )

    # 全文問答用：LlamaParse 抽出的整份文字，不做 markdown 分層。
    # 這是「人工調整區」：擷取任務一律不寫這個欄位，只能從 admin 編輯頁手動填。
    whole_context = models.TextField(
        blank=True,
        help_text="LlamaParse 全文擷取（無 markdown 分層，只保留 <PAGE:N>），供 whole-context 問答使用"
    )

    needs_ocr = models.BooleanField(default=False)
    ocr_done = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=RulebookStatus.choices,
        default=RulebookStatus.PENDING,
    )

    pdf_token_count = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Token count from extracted PDF text (set at parse time)"
    )

    content_languages = models.JSONField(
        default=list, blank=True,
        help_text="Languages detected in PDF, e.g. ['en', 'zh-tw'] (set at parse time)"
    )

    content_hash = models.CharField(max_length=64, blank=True)

    last_error = models.TextField(
        blank=True,
        help_text="最近一次 extract 失敗的錯誤訊息（成功時清空）"
    )

    class Meta:
        indexes = [
            models.Index(fields=["edition", "language", "status"])
        ]

    def __str__(self):
        # return f"{self.edition} / {self.title}"
        return self.title

    def compute_content_hash(self):
        """計算 processed_text 的哈希值"""
        text_to_hash = self.processed_text or ""
        if not text_to_hash:
            return ""
        return hashlib.sha256(text_to_hash.encode("utf-8")).hexdigest()

    def update_content_hash(self):
        """更新 content_hash 欄位"""
        self.content_hash = self.compute_content_hash()
        self.save(update_fields=["content_hash", "updated_at"])
        
    def get_text_for_chunking(self):
        """獲取用於 chunking 的文本"""
        # 優先使用 processed_text，如果為空則使用 extracted_text
        return self.processed_text if self.processed_text else self.extracted_text

    def mark_extract_failed(self, error_msg: str):
        """extract 失敗：標記 FAILED 並留下錯誤訊息，別靜默退回 pending
        （否則 admin 上「排隊中」與「已失敗」無法分辨）。"""
        self.status = RulebookStatus.FAILED
        self.last_error = str(error_msg)[:1000]
        self.save(update_fields=["status", "last_error", "updated_at"])
     

# =============================================================================
# Rulebook Hierarchy Nodes (Recursive Tree)
# =============================================================================

class RulebookNode(TimeStampedModel):
    """
    Rulebook Hierarchy Node - 一個遞迴式的樹狀結構。
    可代表大段落 (Internal Node) 或帶 Embedding 的小分段 (Leaf Node)。
    """

    class VectorSyncStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # ===== 樹狀結構 =====
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        db_index=True,
        help_text="指向本 Table 內的另一 ID，Null 表示頂層 Tag"
    )
    
    rulebook = models.ForeignKey(
        Rulebook,
        on_delete=models.CASCADE,
        related_name="nodes",
        db_index=True,
    )

    # ===== 樹的 Metadata =====
    title = models.CharField(max_length=500, blank=True, help_text="Markdown 中的 Title")
    tag_path = models.CharField(
        max_length=500,
        blank=True,
        db_index=True,
        help_text="Markdown 內的層級路徑，例如 'rules.action.attack'"
    )
    depth = models.IntegerField(default=0, help_text="層級深度: 0, 1, 2, 3...（組裝時排序、控制繼承深度）")
    sibling_order = models.IntegerField(default=0, help_text="同層排序: 1, 2, 3...（同層節點的先後順序）")
    is_leaf = models.BooleanField(default=False, help_text="是否葉節點（有 embedding）")
    
    # ===== 內容與定位 =====
    page = models.IntegerField(null=True, blank=True, help_text="所屬頁數")
    text = models.TextField(blank=True)
    
    ruleset = models.CharField(max_length=100, default='basic', db_index=True)

    # === 冗餘欄位（加速查詢/過濾）===
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="rulebook_nodes",
        null=True,
        editable=False,
    )
    edition = models.ForeignKey(
        Edition,
        on_delete=models.CASCADE,
        related_name="rulebook_nodes",
        null=True,
        editable=False,
    )
    language = models.ForeignKey(
        Tribe,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="rulebook_nodes",
    )

    # === 統計與校驗 ===
    token_count = models.PositiveIntegerField(null=True, blank=True)
    text_hash = models.CharField(max_length=64, blank=True, null=True, db_index=True)

    # === 彈性 Metadata ===
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="player_count 等彈性欄位"
    )

    # === 向量同步欄位 (僅 is_leaf=True 時使用) ===
    vector_point_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="Qdrant point ID"
    )
    vector_collection = models.CharField(
        max_length=100,
        blank=True,
        default="rulebook_nodes",
    )
    embedding_model = models.CharField(max_length=100, blank=True)
    embedding_version = models.CharField(max_length=50, blank=True)
    vector_sync_status = models.CharField(
        max_length=20,
        choices=VectorSyncStatus.choices,
        default=VectorSyncStatus.PENDING,
        db_index=True,
    )
    vector_synced_at = models.DateTimeField(null=True, blank=True)
    vector_last_error = models.TextField(blank=True)

    # 舊欄位保留 (相容性)
    child_index = models.PositiveIntegerField(null=True, blank=True, help_text="舊版序號，現建議使用 sibling_order")

    class Meta:
        ordering = ["rulebook", "depth", "sibling_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["rulebook", "tag_path", "ruleset"],
                name="uq_rulebooknode_path_ruleset",
            )
        ]
        indexes = [
            models.Index(fields=["rulebook", "tag_path", "ruleset"]),
            models.Index(fields=["parent"]),
            models.Index(fields=["is_leaf"]),
            models.Index(fields=["page"]),
            models.Index(fields=["vector_sync_status"]),
        ]

    def __str__(self):
        leaf_str = " (Leaf)" if self.is_leaf else ""
        return f"Node: {self.tag_path or 'ROOT'} - {self.title[:30]}{leaf_str}"

    def save(self, *args, **kwargs):
        # 自動填充冗餘欄位
        if self.rulebook_id and not self.edition_id:
            self.edition = self.rulebook.edition
        if self.edition_id and not self.game_id:
            self.game = self.edition.game
        if self.rulebook_id and not self.language_id:
            self.language = self.rulebook.language
        super().save(*args, **kwargs)

    def get_embedding_text(self) -> str:
        """
        組裝用於 embedding 的文字。
        格式：title (或 tag_path) + 換行 + text
        """
        header = self.title or self.tag_path or ""
        content = self.text or ""
        if header and content:
            return f"{header}\n{content}"
        return content or header

    @property
    def heading_breadcrumb(self) -> str:
        """
        遞迴回溯父節點，建構完整的麵包屑標題路徑。
        例如："Background > Overview" 或 "核心規則 > 戰鬥 > 攻擊"
        若為頂層節點，直接回傳自身 title。
        """
        parts = []
        node = self
        seen = set()  # 防止意外循環
        while node is not None and node.id not in seen:
            seen.add(node.id)
            if node.title:
                parts.append(node.title)
            node = node.parent  # relies on select_related or lazy load
        parts.reverse()
        return " > ".join(parts) if parts else (self.tag_path or "")

    def mark_needs_resync(self):
        self.vector_sync_status = self.VectorSyncStatus.PENDING
        self.save(update_fields=["vector_sync_status", "updated_at"])

    def mark_synced(self, point_id=None, model_name=None, version=None):
        if point_id:
            self.vector_point_id = point_id
        if model_name:
            self.embedding_model = model_name
        if version:
            self.embedding_version = version
        self.vector_sync_status = self.VectorSyncStatus.SYNCED
        self.vector_synced_at = timezone.now()
        self.vector_last_error = ""
        self.save(update_fields=[
            "vector_point_id", "embedding_model", "embedding_version",
            "vector_sync_status", "vector_synced_at", "vector_last_error", "updated_at"
        ])

    def mark_sync_failed(self, error_msg: str):
        self.vector_sync_status = self.VectorSyncStatus.FAILED
        self.vector_last_error = str(error_msg)[:1000]
        self.save(update_fields=["vector_sync_status", "vector_last_error", "updated_at"])



class RulebookQA(TimeStampedModel):
    """
    附加 Q&A：當 RulebookNode 內容不夠準確時，手動或 AI 產生的 Q&A 代替或補充原規則內容。
    """
    class VectorSyncStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rulebook = models.ForeignKey(
        Rulebook, 
        on_delete=models.CASCADE,
        related_name="qas",
        db_index=True
    )
    
    # === 冗餘欄位（加速查詢）===
    game = models.ForeignKey(
        Game, 
        on_delete=models.CASCADE,
        related_name="qas",
        null=True, 
        editable=False,
        help_text="冗餘欄位，自動從 rulebook 填充"
    )
    edition = models.ForeignKey(
        Edition, 
        on_delete=models.CASCADE,
        related_name="qas",
        null=True, 
        editable=False,
        help_text="冗餘欄位，自動從 rulebook 填充"
    )
    language = models.ForeignKey(
        Tribe, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="rulebook_qas"
    )

    # Q&A 內容
    question = models.TextField()
    answer = models.TextField()
    note = models.TextField(blank=True, null=True, help_text="備註")
    source_message = models.ForeignKey(
        'ChatMessage', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="rulebook_qas",
        help_text="來源對話訊息"
    )
    
    token_count = models.PositiveIntegerField(null=True, blank=True)

    # === 向量同步欄位（比照 RulebookNode）===
    vector_point_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="Qdrant point ID"
    )
    
    vector_collection = models.CharField(
        max_length=100, 
        blank=True,
        default="rulebook_qas"
    )
    
    embedding_model = models.CharField(
        max_length=100, 
        blank=True,
        help_text="如: intfloat/multilingual-e5-base"
    )
    
    embedding_version = models.CharField(
        max_length=50, 
        blank=True,
        help_text="自定義版本，如: v1"
    )
    
    vector_sync_status = models.CharField(
        max_length=20,
        choices=VectorSyncStatus.choices,
        default=VectorSyncStatus.PENDING,
        db_index=True
    )
    
    vector_synced_at = models.DateTimeField(null=True, blank=True)
    
    vector_last_error = models.TextField(blank=True)
    text_hash = models.CharField(max_length=64, blank=True, null=True, db_index=True)

    class Meta:
        verbose_name = "Rulebook Q&A"
        verbose_name_plural = "Rulebook Q&As"
        indexes = [
            models.Index(fields=["rulebook"]),
            models.Index(fields=["game"]),
            models.Index(fields=["edition"]),
            models.Index(fields=["language"]),
            models.Index(fields=["vector_sync_status"]),
        ]

    def __str__(self):
        return f"QA: {self.question[:50]}..."

    def save(self, *args, **kwargs):
        # 自動填充冗餘欄位
        if self.rulebook_id and not self.edition_id:
            self.edition = self.rulebook.edition
        if self.edition_id and not self.game_id:
            self.game = self.edition.game
        if self.rulebook_id and not self.language_id:
            self.language = self.rulebook.language
        super().save(*args, **kwargs)

    def mark_needs_resync(self):
        """當內容改變時呼叫"""
        self.vector_sync_status = self.VectorSyncStatus.PENDING
        self.save(update_fields=["vector_sync_status", "updated_at"])

    def get_combined_text(self):
        """獲取用於 embedding 的完整文本"""
        return f"Question: {self.question}\nAnswer: {self.answer}"

    def mark_synced(self, point_id: str):
        self.vector_sync_status = self.VectorSyncStatus.SYNCED
        self.vector_point_id = point_id
        self.vector_synced_at = timezone.now()
        self.vector_last_error = ""
        self.save(update_fields=[
            "vector_point_id", "vector_sync_status", "vector_synced_at", "vector_last_error", "updated_at"
        ])

    def mark_sync_failed(self, error_msg: str):
        self.vector_sync_status = self.VectorSyncStatus.FAILED
        self.vector_last_error = str(error_msg)[:1000]
        self.save(update_fields=["vector_sync_status", "vector_last_error", "updated_at"])


# ---------------------------------------------------------------------------
# Stub kept for historical migrations that reference game.models.rulebook_figure_path
# (RulebookFigure model has been decommissioned)
# ---------------------------------------------------------------------------
def rulebook_figure_path(instance, filename):
    """Legacy upload path stub — RulebookFigure has been removed."""
    import os
    ext = os.path.splitext(filename)[1]
    return f"rulebook_figures/legacy/{uuid.uuid4()}{ext}"


class ChatSession(TimeStampedModel):
    """一場對話（針對某本規則書）"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, null=True, related_name="chat_sessions")
    rulebook = models.ForeignKey(Rulebook, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_sessions"
    )
    user_name = models.CharField(max_length=100, default="Guest")

    # 使用者按「清除對話」是 soft delete：訊息與 session 都保留在 DB
    # （mode/category/token 統計才不會被使用者的清除動作侵蝕），只是從
    # 使用者可見的歷史與「接續對話」邏輯裡濾掉。None = 未刪除。
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

class ChatMessage(TimeStampedModel):
    """對話中的每一條訊息"""
    class Feedback(models.IntegerChoices):
        NONE = 0, "No feedback"
        LIKE = 1, "Like"
        DISLIKE = -1, "Dislike"

    class Category(models.TextChoices):
        """
        問題分類，決定 whole-context 問答走 constants.WHOLE_ROUTING 的哪條 provider 鏈。

        歷史包袱：早期版本用過扁平的 "reasoning"，後來拆成 5 個 "reasoning_*" 子類，
        現在收斂成這三類。舊資料的值原封留在 DB（choices 不是 DB 層約束），
        admin 篩選會顯示成未識別的原始值，正好用來區分新舊樣本。
        """
        SCENARIO = "scenario", "描述了具體遊戲情境"
        RULES    = "rules",    "查規則（提及桌遊常用詞）"
        OTHER    = "other",    "其他（規則書範圍外）"

    class Mode(models.TextChoices):
        RAG   = "rag",   "RAG"
        WHOLE = "whole", "Whole context"

    session = models.ForeignKey(ChatSession, related_name="messages", on_delete=models.CASCADE)
    role = models.CharField(max_length=100) # 'user' or LLM model name
    content = models.TextField()
    sources = models.JSONField(default=list, blank=True) # 儲存當時引用的來源

    # 問題分類（目前只有 whole 模式會分類，RAG 模式留空）
    category = models.CharField(
        max_length=20, choices=Category.choices, blank=True, default="",
        help_text="user prompt 的問題類型；RAG 路徑不分類故留空"
    )
    # 這則訊息走的問答路徑
    mode = models.CharField(
        max_length=20, choices=Mode.choices, default=Mode.RAG,
        help_text="rag = 向量檢索路徑；whole = 整本 whole_context 進 prompt"
    )

    # Feedback
    feedback = models.IntegerField(choices=Feedback.choices, default=Feedback.NONE)
    feedback_text = models.TextField(blank=True, null=True)

    # Token 追蹤
    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)
    total_tokens = models.IntegerField(null=True, blank=True)
    cached_tokens = models.IntegerField(
        null=True, blank=True,
        help_text="prompt_tokens 中命中 implicit prompt cache 的部分（計費較便宜）"
    )

    class Meta:
        indexes = [
            # get_chat_limits() 每次聊天請求都會跑 (role, created_at) 的配額查詢，
            # admin 首頁的 rulesbot_insights 也是同一組條件。
            models.Index(fields=["role", "created_at"]),
        ]


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

class Component(TimeStampedModel):
    """
    記錄某個 Edition 的配件清單（Components List）。
    例如：木製棋子 ×4、卡牌 ×120、6面骰子 ×2。

    material 與 component_type 的選項定義於 module level（COMPONENT_MATERIAL_CHOICES /
    COMPONENT_TYPE_CHOICES），欄位本身不加 choices= 以避免日後擴充選項時需要 migrate。
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(
        Edition, on_delete=models.CASCADE, related_name='components'
    )
    name = models.CharField(
        max_length=200,
        help_text="配件名稱，如 'Player Board'、'Resource Cube'"
    )
    component_type = models.CharField(
        max_length=20,
        blank=True,
        help_text="配件類型，參考 COMPONENT_TYPE_CHOICES"
    )
    material = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="材質，參考 COMPONENT_MATERIAL_CHOICES"
    )
    quantity = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="此配件的數量（不確定可留空）"
    )
    description = models.TextField(
        blank=True,
        help_text="補充說明，如尺寸、特殊備注"
    )

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['edition', 'name'],
                name='uq_component_edition_name',
            )
        ]
        indexes = [
            models.Index(fields=['edition']),
        ]

    def __str__(self):
        qty = f" ×{self.quantity}" if self.quantity else ""
        return f"{self.name}{qty}"


# ---------------------------------------------------------------------------
# Collection / Scraping
# ---------------------------------------------------------------------------

class Collection(TimeStampedModel):
    """會員對某個版本的喜好紀錄 (-4 黑名單 / -1 不喜歡 / 1 有興趣 / 4 擁有或最愛)"""

    class Preference(models.IntegerChoices):
        BEST  = 4
        GOOD  = 3
        BAD   = 2
        WORST = 1

        @property
        def score(self):
            """業務權重 - 改這裡不影響資料庫"""
            # 現在：4, 1, -1, -4
            # 未來：9, 6, 4, 1（直接改這裡）
            return {
                self.BEST:  4,
                self.GOOD:  1,
                self.BAD:   -1,
                self.WORST: -4,
            }[self]    

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(
        'member.Member',
        on_delete=models.CASCADE,
        related_name='collections',
    )
    edition = models.ForeignKey(
        Edition,
        on_delete=models.CASCADE,
        related_name='collections',
    )
    preference = models.SmallIntegerField(choices=Preference.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['member', 'edition'],
                name='uq_collection_member_edition',
            )
        ]
        indexes = [
            models.Index(fields=['member', 'preference']),
            models.Index(fields=['edition', 'preference']),
        ]

    def __str__(self):
        return f"{self.member} → {self.edition} ({self.get_preference_display()})"


class ScrapeLog(TimeStampedModel):
    """一次爬取任務的執行紀錄"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publisher = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name='scrape_logs',
    )
    triggered_by = models.ForeignKey(
        'member.Member',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='triggered_scrape_logs',
    )
    start_at  = models.DateTimeField(null=True, blank=True)
    finish_at = models.DateTimeField(null=True, blank=True)
    qty  = models.PositiveIntegerField(default=0, help_text="爬到的產品筆數")
    logs = models.TextField(blank=True, help_text="執行 log / 錯誤訊息")

    class Meta:
        ordering = ['-start_at']
        indexes = [
            models.Index(fields=['publisher', 'start_at']),
        ]

    def __str__(self):
        return f"ScrapeLog {self.publisher} @ {self.start_at}"


class ScrapedProductStatus(models.TextChoices):
    PENDING   = 'pending',   'Pending'
    REJECTED  = 'rejected',  'Rejected'
    IMPORTED  = 'imported',  'Imported'
    EXPANSION = 'expansion', 'Expansion'


class ScrapedProduct(TimeStampedModel):
    """單筆爬下來的原始商品資料，待人工審核後對應到 Edition"""

    Status = ScrapedProductStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scrapelog = models.ForeignKey(
        ScrapeLog,
        on_delete=models.CASCADE,
        related_name='products',
    )
    raw_data        = models.JSONField(help_text="爬蟲取回的原始資料")
    normalized_data = models.JSONField(default=dict, blank=True, help_text="標準化後的資料")
    status = models.CharField(
        max_length=20,
        choices=ScrapedProductStatus.choices,
        default=ScrapedProductStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        'member.Member',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_scraped_products',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    imported_edition = models.ForeignKey(       # ← 新增
        'Edition',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='source_scraped_products',
        help_text="匯入後對應的 Edition"
    )
    
    # Rankings (BGG specific, added for import tracking)
    rank = models.PositiveIntegerField(null=True, blank=True)
    family_rank = models.PositiveIntegerField(null=True, blank=True)
    party_rank = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['scrapelog', 'status']),
            models.Index(fields=['status', 'reviewed_at']),
        ]


class GameSuggestionStatus(models.TextChoices):
    PENDING  = 'pending',  'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class GameSuggestion(TimeStampedModel):
    """會員推薦新增的桌遊，待人工審核後才會真正建立 Game/Edition/Rulebook。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name="桌遊名")
    rulebook_url = models.URLField(verbose_name="Rulebook 網址")
    barcode = models.CharField(max_length=64, null=True, blank=True, verbose_name="條碼（選填）")
    note = models.TextField(blank=True, verbose_name="備註（選填）")

    # 送出時我們會連去 rulebook_url 確認它真的是 PDF。BGG（Cloudflare 403）與
    # Google Drive/Dropbox 分享連結驗不出來但通常是對的，所以驗不過也照收，
    # 只在這裡標記 False 讓審核的人知道要自己開來看。
    rulebook_url_verified = models.BooleanField(
        default=False,
        verbose_name="Rulebook 連結已驗證為 PDF",
        help_text="False 代表送出當下無法自動確認（雲端硬碟連結、bot 防護…），需人工開啟確認",
    )

    submitted_by = models.ForeignKey(
        'member.Member',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='game_suggestions',
        help_text="提交者（登入會員；帳號被刪除時保留紀錄但設為 null）",
    )

    status = models.CharField(
        max_length=20,
        choices=GameSuggestionStatus.choices,
        default=GameSuggestionStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        'member.Member',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_game_suggestions',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    imported_game = models.ForeignKey(
        'Game',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='source_suggestions',
        help_text="若已人工建立對應 Game，連結於此",
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'created_at'])]


class EditionImportQueueStatus(models.TextChoices):
    SEARCHING = 'searching', '待search'
    REVIEW    = 'review',    '待approval'
    SKIP      = 'skip',      'skip'
    APPROVED  = 'approved',  '已寫入DB'


class EditionImportQueue(TimeStampedModel):
    """版本輸入的工作佇列：先列桌遊名（待search）→ 版本輸入頁送審存下文字（待approval）
    → 設成已寫入DB（approved）才真正跑 run_import 寫入。本機作業用，不進 SYNC_LAYERS。"""

    Status = EditionImportQueueStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name="桌遊名")
    status = models.CharField(
        max_length=20,
        choices=EditionImportQueueStatus.choices,
        default=EditionImportQueueStatus.SEARCHING,
        db_index=True,
    )
    import_text = models.TextField(blank=True, verbose_name="版本輸入預覽",
                                   help_text="版本輸入頁送審時存下的原文，approved 時拿它寫入")
    reviewed_by = models.ForeignKey(
        'member.Member',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_edition_imports',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']   # 依輸入順序
        verbose_name = "Edition import queue"
        verbose_name_plural = "Edition import queue"
        permissions = [
            ("approve_editionimportqueue", "Can approve Edition import queue items (writes to DB)"),
        ]

    def __str__(self):
        return self.name

    def __str__(self):
        return self.name


# =============================================================================
# Rulebook Flowchart (game-flow diagrams generated from RulebookNode tree)
# =============================================================================

def flowchart_content_hash(data) -> str:
    """流程圖內容（React Flow JSON）的穩定 sha256；空圖回空字串。"""
    if not data:
        return ""
    import json
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RulebookFlowchartQuerySet(models.QuerySet):
    def published(self):
        """對外公開中的圖（有 reviewer 核准、且沒被下架）。內容要讀 publication.content。"""
        return self.filter(publication__is_live=True)


class RulebookFlowchart(TimeStampedModel):
    """
    從 RulebookNode + RAG context 產出的桌遊 game-flow Mermaid 流程圖快取。
    每本 rulebook 下以 ruleset 區分,同一 rulebook 的 ruleset 不可重複。
    """

    class Detail(models.TextChoices):
        CONCISE = "concise", "Concise"      # 主流程概覽 ~7-12 nodes
        DETAILED = "detailed", "Detailed"   # 完整條件分支 ~25-40 nodes

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    rulebook = models.ForeignKey(
        Rulebook,
        on_delete=models.CASCADE,
        related_name="flowcharts",
        db_index=True,
    )
    edition = models.ForeignKey(
        Edition,
        on_delete=models.CASCADE,
        related_name="flowcharts",
        null=True, blank=True,
    )
    ruleset = models.CharField(max_length=100, default="basic", db_index=True)
    detail = models.CharField(
        max_length=20, choices=Detail.choices, default=Detail.DETAILED, db_index=True,
    )

    # 「入門圖」：一般會員（含未登入者）看得到內容的流程圖。取代原本以
    # ruleset == "basic" 當免費線的作法——免費線改由這個旗標明確標記，
    # 與 ruleset 名稱脫鉤（見 game/views/original_views.py 的 locked 判斷）。
    initial = models.BooleanField(
        default=True, db_index=True,
        help_text="勾選＝入門圖，一般會員／未登入者可看內容；取消勾選＝只有 subscriber（含 admin）看得到",
    )

    # 瀏覽頁 ruleset pill 的顯示次序：數字小的在前；相同時才依 initial 優先、再依名稱。
    display_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="瀏覽頁 ruleset 顯示次序，數字小的在前（相同時入門圖優先，再依名稱）",
    )

    intermediate_json = models.JSONField(default=dict, blank=True)
    source_chunk_ids = models.JSONField(default=list, blank=True)

    # React Flow topology (auto-generated, no positions)
    # {nodes:[{id,type,data:{label,kind,phase_id}}], edges:[{id,source,target,label,animated}], legends:[...]}
    react_flow_json = models.JSONField(default=dict, blank=True)

    # Human-adjusted React Flow JSON (with positions); null = not yet adjusted
    adjusted_json = models.JSONField(null=True, blank=True, default=None)

    # 公開與否不在這張表：這裡只放編輯中的草稿，公開頁讀的是 reviewer 核准當下
    # 存進 FlowchartPublication 的快照（見 game/flowchart_review.py）。編輯者
    # 能改這張表的任何欄位，所以「已核准」不能是這裡的一個欄位。
    #
    # effective JSON 的 sha256，save() 時一律重算。審核以它判斷「reviewer 看的
    # 是不是現在這一版」與「草稿跟公開版是否相同」。
    content_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    # 最後一次改圖內容的人；LLM 生成時為 None（顯示為系統生成）。審核紀錄會帶上它。
    content_edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True, editable=False,
        on_delete=models.SET_NULL,
        related_name="edited_flowcharts",
    )
    content_edited_at = models.DateTimeField(null=True, blank=True, editable=False)

    # 直接共用顯示本圖的「其他」edition（例如同一遊戲的不同語言版本，流程圖通用）。
    # 與複製（duplicate/copy_to_edition）不同：這裡是同一筆資料被多個 edition 共同引用，
    # 修改本圖會同步反映在所有連結的 edition 上，不會各自獨立。
    linked_editions = models.ManyToManyField(
        Edition, blank=True, related_name="linked_flowcharts",
    )

    # 最近一次 admin 翻譯動作成功的時間（翻譯改由 admin 勾選後手動執行）
    translated_at = models.DateTimeField(null=True, blank=True)

    llm_model = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=20, default="v1")

    # 最新一次「對照 rulebook 全文檢查」結果（LLM，見 game.rag.flowchart.check）。
    # 只保留最新一次，不留歷史；{issues:[{severity,location,description}],summary,model,usage}
    error_check_result = models.JSONField(null=True, blank=True, default=None)
    error_checked_at = models.DateTimeField(null=True, blank=True)

    # 最新一次「獨立自足性檢查」結果（完全不看 rulebook，見 game.rag.flowchart.selfcheck）。
    # 與 error_check_* 職責正交，各存各的才能並排對照：前者查「說錯了嗎」，這裡查
    # 「不看規則書能不能玩」。只保留最新一次；
    # {issues:[{severity,category,location,description,source}],summary,model,usage,structural_count}
    self_check_result = models.JSONField(null=True, blank=True, default=None)
    self_checked_at = models.DateTimeField(null=True, blank=True)

    objects = RulebookFlowchartQuerySet.as_manager()

    class Meta:
        # admin 側欄顯示 "Flowcharts"（預設會由 class 名推成 "Rulebook flowcharts"）
        verbose_name = "flowchart"
        verbose_name_plural = "flowcharts"
        constraints = [
            models.UniqueConstraint(
                fields=["rulebook", "ruleset"],
                name="uq_flowchart_rulebook_ruleset",
            )
        ]
        indexes = [
            models.Index(fields=["rulebook", "detail"]),
        ]
        permissions = [
            ("review_rulebookflowchart", "Can review and publish flowcharts"),
        ]

    def __str__(self):
        return f"Flowchart[{self.detail}] {self.rulebook_id} ({self.ruleset})"

    @property
    def effective_json(self):
        """編輯中的草稿實際內容：有人工調整版就用它，否則用自動生成版。"""
        return self.adjusted_json or self.react_flow_json or {}

    def compute_content_hash(self):
        return flowchart_content_hash(self.effective_json)

    def save(self, *args, **kwargs):
        self.content_hash = self.compute_content_hash()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and (
            {"adjusted_json", "react_flow_json"} & set(update_fields)
        ):
            kwargs["update_fields"] = list(set(update_fields) | {"content_hash"})
        super().save(*args, **kwargs)


class FlowchartPublication(TimeStampedModel):
    """
    流程圖目前對外公開的版本：reviewer 核准當下的內容快照。

    公開頁、sitemap、VPS 同步都讀這裡的 content，不讀 RulebookFlowchart 的草稿，
    所以編輯者核准後再改圖不會影響公開頁，直到 reviewer 再次核准。
    只有 game/flowchart_review.py 會寫這張表（寫入前檢查 review 權限）。
    """

    # PK 就是 flowchart id：同步到 VPS 不會有 PK 漂移。
    flowchart = models.OneToOneField(
        RulebookFlowchart,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="publication",
    )
    content = models.JSONField(default=dict)
    content_hash = models.CharField(max_length=64)
    # 下架設 False 而不刪列：updated_at 會動，delta sync 才能把下架傳到 VPS。
    is_live = models.BooleanField(default=True, db_index=True)
    # 存帳號名稱字串而非 User FK：這張表會同步到 VPS，兩邊的 User id 對不上。
    approved_by_name = models.CharField(max_length=150, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"FlowchartPublication {self.flowchart_id} ({'live' if self.is_live else 'withdrawn'})"


class FlowchartReview(TimeStampedModel):
    """
    流程圖審核紀錄（只增不改，只在本機，不同步到 VPS）。

    核准與退回時存下當下的內容快照，等於「審核過的版本歷史」；兩次審核之間
    的草稿存檔不保留。
    """

    class Action(models.TextChoices):
        SUBMITTED = "submitted", "送審"
        WITHDRAWN = "withdrawn", "收回送審"
        APPROVED = "approved", "核准發布"
        REJECTED = "rejected", "退回"
        UNPUBLISHED = "unpublished", "下架"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flowchart = models.ForeignKey(
        RulebookFlowchart,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    action = models.CharField(max_length=20, choices=Action.choices, db_index=True)
    content_hash = models.CharField(max_length=64, blank=True)
    content = models.JSONField(null=True, blank=True, default=None)
    comment = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="flowchart_review_actions",
    )
    # 審核當下這一版的最後編輯者（RulebookFlowchart.content_edited_by 的快照）
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["flowchart", "-created_at"])]

    def __str__(self):
        return f"FlowchartReview[{self.action}] {self.flowchart_id}"


class FlowchartSuggestion(TimeStampedModel):
    """
    會員針對某張流程圖（RulebookFlowchart，一個 ruleset 一張）填寫的改善建議。

    只收文字，不動圖本身 —— 由 staff 在 admin 讀過後手動調整流程圖，
    流程與 GameSuggestion 一致（pending → approved/rejected）。
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    flowchart = models.ForeignKey(
        RulebookFlowchart,
        on_delete=models.CASCADE,
        related_name="suggestions",
        verbose_name="目標流程圖",
    )
    # 送出當下的版本頁與 ruleset 快照：流程圖之後可能改 ruleset 名稱、或被
    # 連結到別的 edition，留快照才知道會員當初看的是哪一頁的哪個玩法。
    edition = models.ForeignKey(
        Edition,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="flowchart_suggestions",
        verbose_name="送出時所在版本",
    )
    ruleset = models.CharField(
        max_length=100, blank=True, verbose_name="ruleset（送出時快照）",
    )

    content = models.TextField(verbose_name="改善建議")

    submitted_by = models.ForeignKey(
        'member.Member',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='flowchart_suggestions',
        help_text="提交者（登入會員；帳號被刪除時保留紀錄但設為 null）",
    )

    status = models.CharField(
        max_length=20,
        choices=GameSuggestionStatus.choices,
        default=GameSuggestionStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        'member.Member',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_flowchart_suggestions',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self):
        return f"FlowchartSuggestion {self.flowchart_id} ({self.ruleset})"


class FlowchartTextTranslation(TimeStampedModel):
    """
    flowchart 內單段文字的多語（en/zh/ja/fr/de/es）翻譯快取。
    以 text_hash（原文 sha256）去重，跨所有圖表共用，避免重複呼叫 DeepL。
    """

    text_hash = models.CharField(max_length=64, unique=True, db_index=True)
    source_text = models.TextField()
    source_lang = models.CharField(max_length=10)
    # {"en": "...", "zh": "...", "ja": "...", "fr": "...", "de": "...", "es": "..."}
    # 含來源語本身（直接存原文）。
    translations = models.JSONField(default=dict, blank=True)
    # 人工修訂鎖定：True 時強制重譯會跳過此列，不被機器翻譯覆蓋
    is_manual = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return f"FlowchartText[{self.source_lang}] {self.source_text[:30]}"


# 日文小型拗音假名（ゃゅょ 及母音行 ぁぃぅぇぉ 等）不算獨立一拍，會併入前一個假名
# 一起發音（例如「きゃ」算 1 拍，不是 2 拍）。促音っ/ッ、長音符ー、ん 則各自算 1 拍。
_JA_SMALL_YOON = set("ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ")


def _count_japanese_mora(text: str) -> int:
    """
    粗略估算日文「拍」數。漢字缺乏讀音資訊，無法從純文字精確算拍，
    以每個漢字算 1 拍近似（實際發音通常 1-3 拍，此為簡化估計，僅供 admin 參考）。
    """
    count = 0
    for ch in text:
        if ch in _JA_SMALL_YOON:
            continue  # 併入前一拍，不重複計算
        if ch.isspace():
            continue
        if not ch.isalnum() and not ("぀" <= ch <= "ヿ") and not ("一" <= ch <= "鿿"):
            continue  # 標點符號等不計入
        count += 1
    return count


def count_script_text_length(text: str, language: str) -> int:
    """依語言決定計數方式：中文以字計算、日文以拍估算、其餘語言以 word 計算。"""
    if not text:
        return 0
    if language == "zh":
        return len(re.sub(r"\s+", "", text))
    if language == "ja":
        return _count_japanese_mora(text)
    return len(text.split())


class RulebookScript(TimeStampedModel):
    """
    Game master 教學講稿（5 分鐘讀完）快取，每本 rulebook 下以 ruleset 區分。
    host_persona / story_atmosphere 是 rulebook 以外的人工創意輸入，生成前先在 admin 填好。
    是否對前台公開由 is_published 人工勾選決定，與生成狀態脫鉤。
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft (not generated)"
        GENERATING = "generating", "Generating"
        GENERATED = "generated", "Generated"
        FAILED = "failed", "Generation failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    rulebook = models.ForeignKey(
        Rulebook, on_delete=models.CASCADE, related_name="scripts", db_index=True,
    )
    edition = models.ForeignKey(
        Edition, on_delete=models.CASCADE, related_name="scripts",
        null=True, blank=True,
    )
    ruleset = models.CharField(max_length=100, default="basic", db_index=True)

    # ── 人工創意輸入（生成前填寫）──
    host_persona = models.TextField(
        blank=True, help_text="主持人角色、崗位、個性等描述（約 3 行），用來控制講稿語氣與用字",
    )
    player_persona = models.TextField(
        blank=True, help_text="玩家在遊戲中扮演的角色描述（約 3 行），用來讓主持人向玩家說明他們的身份",
    )
    story_atmosphere = models.TextField(
        blank=True, help_text="背景故事氛圍描述（約 3 行，rulebook 以外的創意設定）",
    )
    language = models.ForeignKey(
        Tribe, on_delete=models.PROTECT, related_name="scripts",
        help_text="講稿輸出語言",
    )

    # ── 生成輸出 ──
    title = models.CharField(max_length=200, blank=True)
    script_text = models.TextField(blank=True)
    adjusted_title = models.CharField(max_length=200, blank=True)
    adjusted_text = models.TextField(null=True, blank=True, default=None)
    human_adjust = models.BooleanField(default=False)
    source_chunk_ids = models.JSONField(default=list, blank=True)
    source_flowchart = models.ForeignKey(
        RulebookFlowchart, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="scripts",
    )

    # 直接共用顯示本講稿的「其他」edition（例如同一遊戲的不同語言版本，講稿通用）。
    # 與複製不同：這裡是同一筆資料被多個 edition 共同引用，修改講稿會同步反映在
    # 所有連結的 edition 上，不會各自獨立（比照 RulebookFlowchart.linked_editions）。
    linked_editions = models.ManyToManyField(
        Edition, blank=True, related_name="linked_scripts",
    )

    # ── 溯源（純參考資訊，不驅動任何判斷）──
    llm_model = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    generation_error = models.TextField(blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True,
    )

    # 是否對前台公開；人工勾選，不受重新生成或 flowchart 版本更新影響
    is_published = models.BooleanField(
        default=False, db_index=True,
        help_text="是否對前台公開；人工勾選，不受重新生成或 flowchart 版本更新影響",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rulebook", "ruleset", "language"],
                name="uq_script_rulebook_ruleset_language",
            )
        ]

    def __str__(self):
        return f"Script {self.rulebook_id} ({self.ruleset}, {self.language_id and self.language.language})"

    @property
    def effective_title(self):
        return self.adjusted_title if self.adjusted_title else self.title

    @property
    def effective_text(self):
        return self.adjusted_text if self.adjusted_text else self.script_text

    @property
    def effective_text_length(self) -> int:
        """依 language 計數目前生效內容的長度（中文以字、日文以拍估算、其餘以 word 計算）。"""
        lang_code = self.language.language if self.language_id else ""
        return count_script_text_length(self.effective_text, lang_code)


# ─── Rulebook 刪除時連帶清理 PDF 檔與 Qdrant 向量 ───
from django.db import transaction  # noqa: E402
from django.db.models.signals import post_delete  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_delete, sender=Rulebook)
def cleanup_rulebook_assets(sender, instance, **kwargs):
    """Django 刪 model 不會刪 FileField 檔案，也不知道 Qdrant 的存在，這裡補上。

    兩者都等 transaction commit 後才動手（rollback 時不該刪），失敗只記 log，
    不能讓 admin 刪除流程跟著掛掉。批次刪除、cascade（Edition 被刪）也會觸發。
    """
    import logging
    log = logging.getLogger(__name__)
    rb_id = str(instance.pk)
    file_name = instance.file.name if instance.file else ""
    storage = instance.file.storage if file_name else None

    def _cleanup():
        if file_name:
            try:
                storage.delete(file_name)
            except Exception:
                log.exception("Rulebook %s: 刪除 PDF 檔失敗 (%s)", rb_id, file_name)
        try:
            from game.rag.qdrant_service import get_qdrant_service
            qdrant = get_qdrant_service()
            for coll in (
                getattr(settings, "QDRANT_NODES_COLLECTION_NAME", "rulebook_nodes"),
                getattr(settings, "QDRANT_QA_COLLECTION_NAME", "rulebook_qas"),
            ):
                qdrant.delete_rulebook_vectors(rb_id, collection_name=coll)
        except Exception:
            log.exception("Rulebook %s: 刪除 Qdrant 向量失敗", rb_id)

    transaction.on_commit(_cleanup)


# ─── Sync model (imported here so Django discovers it for migrations) ───
from game.sync_models import GameSyncLog  # noqa: E402, F401