from django.contrib import admin, messages
from .models import EditionUnlock, Member, UserActivity, Tier
from django.contrib.auth.models import Group, User
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from translation.models import Tribe  # 导入 Tribe 以便关联
from .features import FEATURES, FeatureStatus
from .forms import TierLimitsForm

# 定义 MemberAdmin
class MemberAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id', 'tier', 'tier_new', 'tribe', 'registration_date', 'source')  # 在列表页显示的字段
    list_filter = ('tribe',)  # 过滤器
    search_fields = ('id__username',)  # 允许按用户名搜索
    autocomplete_fields = ('tribe',)  # 让 Tribe 选择框支持自动补全
    
    def registration_date(self, obj):
        """显示用户注册日期"""
        return obj.id.date_joined if obj.id else None
    registration_date.short_description = '註冊日期'

    def user_id(self, obj):
        """显示用户ID"""
        return obj.id.id if obj.id else None
    user_id.short_description = 'User ID'

# 取消默认的 User 注册（因为我们要扩展 User）
admin.site.unregister(User)


# Group：加一個把群組（名稱＋權限）推到 VPS 的 action。
admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin):
    actions = ["sync_groups_vps_action"]

    def has_sync_permission(self, request):
        # 推上正式站等於直接改正式站的權限設定，只給 superuser
        return request.user.is_superuser

    @admin.action(
        description="📤 Sync selected Groups to VPS（覆寫 VPS 同名群組的權限，不動成員）",
        permissions=["sync"],
    )
    def sync_groups_vps_action(self, request, queryset):
        from game.sync_service import GameSyncService

        sync_log = GameSyncService().sync_groups(queryset)
        names = ", ".join(queryset.values_list("name", flat=True))

        if sync_log.status == "success":
            if sync_log.records_sent == 0:
                messages.info(request, "ℹ️ 沒有選取任何 Group，未送出。")
            else:
                messages.success(
                    request, f"✅ 已同步 {sync_log.records_sent} 個 Group 到 VPS：{names}"
                )
        elif sync_log.status == "partial":
            messages.warning(request, f"⚠️ Group sync 部分成功: {sync_log.error}")
        else:
            messages.error(request, f"❌ Group sync 失敗: {sync_log.error}")


# 扩展 UserAdmin，使得在 User 编辑页面中也能管理 Member 相关数据
class MemberInline(admin.StackedInline):  # 以内联方式显示 Member 信息
    model = Member
    can_delete = False
    verbose_name_plural = 'Member Info'
    fk_name = 'id'

class UserAdmin(BaseUserAdmin):
    inlines = (MemberInline, )  # 让 UserAdmin 也能管理 Member 信息

# 重新注册 User，并附加 Member 管理
admin.site.register(User, UserAdmin)

# 直接注册 Member 管理（如果你想独立管理 Member）
admin.site.register(Member, MemberAdmin)


@admin.register(EditionUnlock)
class EditionUnlockAdmin(admin.ModelAdmin):
    """永久解鎖的人工後門。

    使用者端是不可逆的（免費名額只在該版本還沒有已發布流程圖時退得回，付費
    的完全不可逆），而且付費那條牽涉金流，所以客服一定要有地方查帳與手動
    修正——選錯版本的退款／改指定只能從這裡做。

    刪除一列就等於收回權益，請確認退款已處理再刪。
    """
    list_display = ('member', 'edition', 'source', 'transaction', 'created_at')
    list_filter = ('source', 'created_at')
    search_fields = ('member__id__username', 'edition__name')
    autocomplete_fields = ('member', 'edition')
    readonly_fields = ('created_at',)
    list_select_related = ('member', 'edition', 'transaction')


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('member', 'session_id', 'event_type', 'page', 'lang', 'meta', 'created_at')

@admin.register(Tier)
class TierAdmin(admin.ModelAdmin):
    form = TierLimitsForm
    list_display = ('code', 'name', 'limits_summary')

    _active_fields = tuple(f"feat__{k}" for k, s in FEATURES.items() if s.status is FeatureStatus.ACTIVE)
    _unreferenced_fields = tuple(f"feat__{k}" for k, s in FEATURES.items() if s.status is FeatureStatus.UNREFERENCED)

    fieldsets = (
        (None, {'fields': ('code', 'name')}),
        ('Feature Flags (Active)', {'fields': _active_fields}),
        ('Feature Flags (Unreferenced — 確認後再考慮刪除)', {
            'fields': _unreferenced_fields,
            'classes': ('collapse',),
        }),
    )

    @admin.display(description="Active Limits")
    def limits_summary(self, obj):
        if not isinstance(obj.limits, dict):
            return "—"
        active = {k: obj.limits.get(k) for k, s in FEATURES.items() if s.status is FeatureStatus.ACTIVE}
        return ", ".join(f"{k}={v}" for k, v in active.items()) or "—"

    @admin.action(description="📤 Sync selected Tiers to VPS (upsert only, no deletes)")
    def sync_tiers_vps_action(self, request, queryset):
        from game.sync_service import GameSyncService

        sync_log = GameSyncService().sync_tiers(queryset)
        codes = ", ".join(queryset.values_list("code", flat=True))

        if sync_log.status == "success":
            if sync_log.records_sent == 0:
                messages.info(request, "ℹ️ 沒有選取任何 Tier，未送出。")
            else:
                messages.success(
                    request,
                    f"✅ 已同步 {sync_log.records_sent} 個 Tier 設定到 VPS：{codes}"
                )
        elif sync_log.status == "partial":
            messages.warning(request, f"⚠️ Tier sync 部分成功: {sync_log.error}")
        else:
            messages.error(request, f"❌ Tier sync 失敗: {sync_log.error}")

    actions = ["sync_tiers_vps_action"]