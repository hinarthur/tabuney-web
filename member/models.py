import json
import logging
import uuid

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from translation.models import Tribe
from django.contrib.postgres.fields import ArrayField

from .features import FEATURES, FeatureKind

logger = logging.getLogger(__name__)

class Tier(models.Model):
    code = models.CharField(
        max_length=20,
        primary_key=True,
        help_text="等級代碼，如 'free', 'basic'"
    )
    name = models.CharField(max_length=50, help_text="顯示名稱")

    limits = models.JSONField(
        default=dict,
        help_text="用量限制：0=disabled, -1=無限, 正數=上限"
    )    


    def __str__(self):
        return f"{self.name} ({self.code})"

class Member(models.Model):
    id = models.OneToOneField(User, to_field="id", primary_key=True, on_delete=models.CASCADE, db_column="id")
    avatar = models.URLField(null=True, blank=True, help_text="Google 頭像 URL")
    tribe = models.ForeignKey(Tribe, on_delete=models.SET_NULL, null=True, blank=True, default=1)
        
    # tier = models.CharField(
    #     max_length=12, default="A", null=False, blank=False,
    #     choices=[('A', 'Free'), ('B', 'Basic')]
    # )
    # 新的 ForeignKey（先允許 null，遷移後再改）
    tier_new = models.ForeignKey(
        'Tier',
        on_delete=models.PROTECT,
        null=True,  # 暫時允許 null
        blank=True,
        related_name='members',
        db_column='tier_new',  # 用新的資料庫欄位
        help_text="會員等級"
    )
    
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True, help_text="Google 使用者唯一識別碼")
    source = models.CharField(max_length=20, default='web', help_text="註冊來源：web, app 等")
    feedlist_style = models.CharField(max_length=32, null=True, blank=True)
    feedlist_lang = ArrayField(models.CharField(max_length=10), null=True, blank=True, default=list,)
    stripe_customer_id = models.CharField(max_length=64, null=True, blank=True)
    
    def __str__(self):
        return self.id.username  # 返回關聯 User 的 username

    class Meta:
        verbose_name = "Member"
        verbose_name_plural = "Members"
     
    @property
    def tier(self):
        return self.tier_new.code if self.tier_new_id else 'free'

    @property
    def tier_code_for_api(self):
        """給 API 用的等級代碼"""
        return self.tier

    # ── Tier feature 存取（唯一入口，見 member/features.py 的 registry）──

    def _raw_limits(self) -> dict:
        """取得 tier_new.limits 並正規化為 dict。任何解析失敗都 log 後回傳 {}，
        讓呼叫端改用 registry default，而不是整批靜默鎖死或整批靜默放行。"""
        if not self.tier_new_id:
            return {}
        limits = self.tier_new.limits
        if isinstance(limits, str):
            try:
                limits = json.loads(limits)
            except (TypeError, ValueError) as e:
                logger.error(
                    "Member %s: tier %s limits 是無法解析的 JSON 字串：%s",
                    self.id_id, self.tier_new_id, e,
                )
                return {}
        if not isinstance(limits, dict):
            logger.error(
                "Member %s: tier %s limits 不是 dict（型別 %r）",
                self.id_id, self.tier_new_id, type(limits),
            )
            return {}
        return limits

    def can(self, key: str) -> bool:
        """BOOL 型 feature 查詢：tier.limits 缺此 key 時回退 registry default。
        key 未在 member/features.py 註冊時 log warning 並 fail closed。"""
        spec = FEATURES.get(key)
        if spec is None:
            logger.warning("Member.can(): 未註冊的 feature key %r", key)
            return False
        if spec.kind is not FeatureKind.BOOL:
            logger.warning("Member.can(): key %r 是 kind=%s，不是 BOOL", key, spec.kind)
        raw = self._raw_limits().get(key, spec.default)
        try:
            return int(raw) != 0
        except (TypeError, ValueError):
            logger.error("Member.can(): key %r 的值 %r 無法轉成數字", key, raw)
            return False

    def limit(self, key: str) -> int:
        """QUOTA 型 feature 查詢，-1 代表無限。tier.limits 缺此 key 時回退
        registry default。key 未在 member/features.py 註冊時 log warning 並回傳 0。"""
        spec = FEATURES.get(key)
        if spec is None:
            logger.warning("Member.limit(): 未註冊的 feature key %r", key)
            return 0
        raw = self._raw_limits().get(key, spec.default)
        try:
            return int(raw)
        except (TypeError, ValueError):
            logger.error("Member.limit(): key %r 的值 %r 無法轉成數字", key, raw)
            return 0

    @property
    def tier_code(self) -> str:
        """統一的顯示用等級代碼正規化（取代 views 內重複的判斷邏輯）。
        'basic' 併入 'member'；其餘 tier code（'free'/'member'/'subscriber'/
        'admin' 等）原樣回傳，不會因為不在白名單內就被吃掉。"""
        if not self.tier_new_id:
            return 'free'
        code = self.tier_new.code
        return 'member' if code == 'basic' else code

    @property
    def is_subscriber_or_higher(self) -> bool:
        """tier code 是否為 subscriber 以上（含 admin）。

        原本是流程圖付費閘門的判斷式，現已改由 tier feature
        'flowchart_non_initial' 決定（見 member/features.py），這裡不再有
        呼叫端；保留是為了讓日後真的需要「以 tier 階層判斷」的地方有統一
        寫法，而不是各自回去做 current_tier == 'subscriber' 的字串比對
        （那種寫法會把 'admin' tier 排除在外）。"""
        return self.tier_code in ('subscriber', 'admin')

    # ── Per-edition 永久解鎖（見 EditionUnlock）──────────────────────────
    #
    # 這是全站第一個 per-object 權限。tier feature 是「這個等級能不能做這件
    # 事」，這裡是「這個人對這一款 edition 能不能做這件事」，兩者是 OR 關係：
    # 呼叫端寫 unlocked or member.can(...)，不要把其中一邊改寫成另一邊。

    def unlocked_edition_ids(self) -> set:
        """本會員已永久解鎖的 edition id 集合（免費名額 + 付費加購一起算）。

        每個 Member 實例只查一次並快取在實例上：搜尋頁一次要問 20 張卡片，
        流程圖頁面也會問好幾次，逐次查會變成 N+1。實例快取而非 cached_property，
        是為了讓 pick/release 之後能用 invalidate_unlocked_cache() 明確作廢。
        """
        if not hasattr(self, '_unlocked_edition_ids'):
            self._unlocked_edition_ids = set(
                self.edition_unlocks.values_list('edition_id', flat=True)
            )
        return self._unlocked_edition_ids

    def invalidate_unlocked_cache(self):
        """選取／退回／購買之後呼叫，讓同一個 request 內後續的查詢讀到新狀態。"""
        self.__dict__.pop('_unlocked_edition_ids', None)

    def has_unlocked(self, edition_id) -> bool:
        """edition_id 可以是 UUID 或字串。

        Edition.pk 是 UUID，但呼叫端來源很雜（URL 轉換器給 UUID、表單 POST
        給字串、JSON payload 給字串），不正規化的話 'xxx' != UUID('xxx') 會
        靜默地把已解鎖的人當成沒解鎖——那是 fail-closed 但完全看不出原因的
        那種錯。
        """
        if edition_id is None:
            return False
        if not isinstance(edition_id, uuid.UUID):
            try:
                edition_id = uuid.UUID(str(edition_id))
            except (TypeError, ValueError):
                return False
        return edition_id in self.unlocked_edition_ids()

    def free_unlock_usage(self) -> tuple[int, int]:
        """(已用掉的免費名額, 免費名額上限)。上限 -1 代表無限。

        只數 source='free'：付費加購不佔名額，否則買越多反而越不能免費選。
        """
        used = self.edition_unlocks.filter(source=EditionUnlock.Source.FREE).count()
        return used, self.limit('edition_unlock')

    def can_pick_free(self) -> bool:
        used, quota = self.free_unlock_usage()
        return quota == -1 or used < quota

@receiver(post_save, sender=User)
def create_user_member(sender, instance, created, **kwargs):
    if created:
        Member.objects.create(id=instance)

@receiver(post_save, sender=User)
def save_user_member(sender, instance, **kwargs):
    instance.member.save()


class EditionUnlock(models.Model):
    """會員對單一 Edition 的永久解鎖。

    解鎖內容：該 edition 流程圖的全螢幕／列印／步驟導覽、所有非入門 ruleset，
    以及該 edition 的 Rulesbot 無限查問。**不含 GM 講稿**（script 仍是 tier
    feature 'script' 說了算）。

    與 tier 完全脫鉤，這是刻意的：名額是「已兌換的權益」，不是「訂閱期間的
    能力」。subscriber 會籍過期降級成 free 之後這些列仍然有效，查詢端也絕不
    該再去看 tier。要做成會過期的東西時請新增欄位，不要改成讀 tier。

    source='free' 佔用 tier feature 'edition_unlock' 的名額（預設 3），且在該
    edition 完全沒有已發布流程圖時可以退回重選（等於還沒東西可解鎖）；
    source='paid' 不佔名額也不可退回——購買入口在該 edition 沒有已發布流程圖
    時根本不會出現（驗證在 commerce.views.create_edition_unlock_session），
    所以付費列一建立就必然是已定案狀態。

    FK 用字串而非 import：member 目前只 import translation，直接 import
    game/commerce 會做出模組層的循環相依。
    """

    class Source(models.TextChoices):
        FREE = 'free', '免費名額'
        PAID = 'paid', 'US$1 加購'

    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='edition_unlocks',
    )
    edition = models.ForeignKey(
        'game.Edition', on_delete=models.CASCADE, related_name='member_unlocks',
    )
    source = models.CharField(
        max_length=8, choices=Source.choices, default=Source.FREE, db_index=True,
        help_text="free=用掉一個免費名額；paid=US$1 單品加購",
    )
    transaction = models.ForeignKey(
        'commerce.Transaction', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='edition_unlocks',
        help_text="付費加購的金流憑證；免費名額為空",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Edition Unlock"
        verbose_name_plural = "Edition Unlocks"
        constraints = [
            models.UniqueConstraint(
                fields=['member', 'edition'],
                name='uq_edition_unlock_member_edition',
            ),
        ]
        indexes = [models.Index(fields=['member'])]

    def __str__(self):
        return f"{self.member} → {self.edition} ({self.source})"


class UserActivity(models.Model):
    member = models.ForeignKey(Member, null=True, blank=True, on_delete=models.SET_NULL)
    session_id = models.CharField(max_length=64, null=True, blank=True)
    event_type = models.CharField(max_length=32)  # e.g. 'open_app', 'close_app', 'page_view', 'source_click'
    page = models.CharField(max_length=128, null=True, blank=True)
    lang = models.CharField(max_length=16, null=True, blank=True)
    meta = models.JSONField(null=True, blank=True)  # 附加資料
    created_at = models.DateTimeField(auto_now_add=True)