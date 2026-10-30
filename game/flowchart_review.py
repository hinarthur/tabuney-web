"""
流程圖審核發布。

RulebookFlowchart 只放編輯中的草稿；對外公開的是 reviewer 核准當下存進
FlowchartPublication 的快照。這個模組是唯一會寫 FlowchartPublication 的地方，
每個動作都先檢查權限：
  - 送審：game.change_rulebookflowchart（編輯者）
  - 核准／退回／下架：game.review_rulebookflowchart（reviewer；superuser 天生具備）

reviewer 可以核准自己編輯過的圖，但每筆 FlowchartReview 都會記下最後編輯者。
"""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from game.models import FlowchartPublication, FlowchartReview, RulebookFlowchart

EDIT_PERM = "game.change_rulebookflowchart"
REVIEW_PERM = "game.review_rulebookflowchart"


class ReviewError(Exception):
    """審核動作因內容狀態不成立而失敗（不是權限問題）。訊息直接顯示給使用者。"""


def can_review(user) -> bool:
    return bool(user and user.is_active and user.has_perm(REVIEW_PERM))


def can_edit(user) -> bool:
    return bool(user and user.is_active and user.has_perm(EDIT_PERM))


def mark_edited(chart, user):
    """寫入圖內容的地方呼叫：記下最後編輯者。user=None 表示系統（LLM 生成）。"""
    chart.content_edited_by = user if (user and user.is_authenticated) else None
    chart.content_edited_at = timezone.now()


EDIT_FIELDS = ["content_edited_by", "content_edited_at"]


# ─── 狀態 ──────────────────────────────────────────

class State:
    DRAFT = "draft"                         # 從未上線（或已下架）且沒有待審
    PENDING = "pending"                     # 目前這一版已送審
    REJECTED = "rejected"                   # 目前這一版被退回
    LIVE = "live"                           # 草稿與公開版相同
    LIVE_WITH_CHANGES = "live_with_changes" # 已公開，但草稿有尚未核准的修改


STATE_LABELS = {
    State.DRAFT: "草稿",
    State.PENDING: "待審",
    State.REJECTED: "退回",
    State.LIVE: "已發布",
    State.LIVE_WITH_CHANGES: "已發布・有修改",
}


def get_publication(chart):
    try:
        return chart.publication
    except FlowchartPublication.DoesNotExist:
        return None


def latest_review(chart):
    return chart.reviews.order_by("-created_at").first()


def review_state(chart, latest=None) -> str:
    pub = get_publication(chart)
    if pub and pub.is_live and pub.content_hash == chart.content_hash:
        return State.LIVE
    latest = latest if latest is not None else latest_review(chart)
    if latest and latest.content_hash == chart.content_hash:
        if latest.action == FlowchartReview.Action.SUBMITTED:
            return State.PENDING
        if latest.action == FlowchartReview.Action.REJECTED:
            return State.REJECTED
    if pub and pub.is_live:
        return State.LIVE_WITH_CHANGES
    return State.DRAFT


# ─── 動作 ──────────────────────────────────────────

def _locked(chart):
    """鎖住這張圖再重新讀一次，避免和編輯器存檔交錯。"""
    return RulebookFlowchart.objects.select_for_update().get(pk=chart.pk)


def _log(chart, action, actor, comment="", content=None):
    return FlowchartReview.objects.create(
        flowchart=chart,
        action=action,
        content_hash=chart.content_hash,
        content=content,
        comment=comment,
        actor=actor,
        last_editor_id=chart.content_edited_by_id,
    )


def _check_expected(chart, expected_hash):
    if not expected_hash or expected_hash != chart.content_hash:
        raise ReviewError("流程圖在你檢視之後被修改過，請重新載入審核頁確認最新內容後再操作。")


def submit(chart, user, comment=""):
    if not can_edit(user):
        raise PermissionDenied("沒有編輯流程圖的權限")
    with transaction.atomic():
        chart = _locked(chart)
        if not chart.content_hash:
            raise ReviewError("空白流程圖不能送審。")
        pub = get_publication(chart)
        if pub and pub.is_live and pub.content_hash == chart.content_hash:
            raise ReviewError("目前內容與公開版相同，不需要送審。")
        return _log(chart, FlowchartReview.Action.SUBMITTED, user, comment)


def withdraw(chart, user, comment=""):
    """編輯者收回送審，回到可繼續編輯的草稿。只有「目前這一版正在待審」時才成立。"""
    if not can_edit(user):
        raise PermissionDenied("沒有編輯流程圖的權限")
    with transaction.atomic():
        chart = _locked(chart)
        if review_state(chart) != State.PENDING:
            raise ReviewError("這張流程圖目前沒有待審的送審，可能已被審核或已收回。")
        return _log(chart, FlowchartReview.Action.WITHDRAWN, user, comment)


def restore_published(chart, user):
    """把草稿還原成目前的公開版（丟掉草稿上尚未核准的修改）。"""
    if not can_edit(user):
        raise PermissionDenied("沒有編輯流程圖的權限")
    with transaction.atomic():
        chart = _locked(chart)
        pub = get_publication(chart)
        if not pub or not pub.is_live:
            raise ReviewError("這張流程圖目前沒有公開版可還原。")
        if pub.content_hash == chart.content_hash:
            raise ReviewError("草稿已經和公開版相同。")
        chart.adjusted_json = pub.content
        mark_edited(chart, user)
        chart.save(update_fields=["adjusted_json", "updated_at", *EDIT_FIELDS])
        return chart


def approve(chart, reviewer, expected_hash, comment=""):
    if not can_review(reviewer):
        raise PermissionDenied("沒有審核流程圖的權限")
    with transaction.atomic():
        chart = _locked(chart)
        _check_expected(chart, expected_hash)
        content = chart.effective_json
        if not content:
            raise ReviewError("空白流程圖不能發布。")
        now = timezone.now()
        FlowchartPublication.objects.update_or_create(
            flowchart=chart,
            defaults=dict(
                content=content,
                content_hash=chart.content_hash,
                is_live=True,
                approved_by_name=reviewer.get_username(),
                approved_at=now,
            ),
        )
        return _log(chart, FlowchartReview.Action.APPROVED, reviewer, comment, content)


def reject(chart, reviewer, expected_hash, comment=""):
    if not can_review(reviewer):
        raise PermissionDenied("沒有審核流程圖的權限")
    with transaction.atomic():
        chart = _locked(chart)
        _check_expected(chart, expected_hash)
        return _log(chart, FlowchartReview.Action.REJECTED, reviewer, comment, chart.effective_json)


def unpublish(chart, reviewer, comment=""):
    if not can_review(reviewer):
        raise PermissionDenied("沒有審核流程圖的權限")
    with transaction.atomic():
        chart = _locked(chart)
        pub = get_publication(chart)
        if not pub or not pub.is_live:
            raise ReviewError("這張流程圖目前沒有公開。")
        pub.is_live = False
        pub.save(update_fields=["is_live", "updated_at"])
        return _log(chart, FlowchartReview.Action.UNPUBLISHED, reviewer, comment)


# ─── 審核頁用的差異摘要 ─────────────────────────────

@dataclass
class TextDiff:
    added: list
    removed: list


def text_diff(old_json, new_json) -> TextDiff:
    """以節點／連線上的文字為單位，比對公開版與草稿多了／少了哪些文字。"""
    from game.rag.flowchart.i18n import collect_texts

    old = [t for t in collect_texts(old_json or {}) if t and t.strip()]
    new = [t for t in collect_texts(new_json or {}) if t and t.strip()]
    old_set, new_set = set(old), set(new)
    return TextDiff(
        added=[t for t in dict.fromkeys(new) if t not in old_set],
        removed=[t for t in dict.fromkeys(old) if t not in new_set],
    )


# ─── 發布前多語預覽 ─────────────────────────────────
#
# 在真實的公開流程圖頁上看草稿：/<lang>/games/<slug>/flowchart/?preview=<flowchart_id>。
# 只有具備 view 權限的人會啟用（見 EditionDetailView._flowchart_context），
# 其他人帶這個參數只會看到公開版。

PREVIEW_PARAM = "preview"
VIEW_PERM = "game.view_rulebookflowchart"


def can_preview(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active and user.has_perm(VIEW_PERM))


def preview_edition(chart):
    """預覽要掛在哪個版本頁：圖自己的 edition，沒有 slug 時用第一個有 slug 的共用 edition。"""
    edition = getattr(chart.rulebook, "edition", None)
    if edition is not None and edition.slug:
        return edition
    return chart.linked_editions.exclude(slug__isnull=True).exclude(slug="").first()


def preview_urls(chart, edition=None):
    """
    各語言的預覽網址 [(語言代碼, 顯示名稱, 網址), ...]；沒有可掛的版本頁時回 []。

    語言由網址前綴決定（英文沒有前綴），所以每個語言各 reverse 一次。站上原本的
    語言選單只帶路徑、會丟掉查詢參數，預覽頁的語言切換要用這裡產生的網址。
    """
    from django.conf import settings
    from django.urls import reverse
    from django.utils import translation

    edition = edition or preview_edition(chart)
    if edition is None or not edition.slug:
        return []
    urls = []
    for code, label in settings.LANGUAGES:
        with translation.override(code):
            path = reverse(
                "games:edition-detail-tab", kwargs={"slug": edition.slug, "tab": "flowchart"},
            )
        urls.append((code, label, f"{path}?{PREVIEW_PARAM}={chart.pk}"))
    return urls


def missing_translation_count(rf_json, lang) -> int:
    """草稿裡在 lang 下沒有譯文、會以原文顯示的文字段數。"""
    from game.models import FlowchartTextTranslation
    from game.rag.flowchart.i18n import _norm_lang, collect_texts, compute_hash

    texts = [t for t in collect_texts(rf_json or {}) if t and t.strip()]
    if not texts:
        return 0
    target = _norm_lang(lang)
    hashes = {compute_hash(t) for t in texts}
    translated = {
        row.text_hash
        for row in FlowchartTextTranslation.objects.filter(text_hash__in=hashes)
        if row.translations.get(target)
    }
    return len(hashes - translated)
