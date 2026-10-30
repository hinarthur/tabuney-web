"""Tier.limits 的唯一合法 key 清單（single source of truth）。

Member.can() / Member.limit() 只認得這裡註冊的 key；Tier admin 表單也是依這份
清單動態產生欄位。新增一個 tier 能力時，只需要在這裡加一筆 FeatureSpec——
不需要 migration，也不需要另外去改任何 view 的解析邏輯。

不要在別的地方直接讀 tier.limits——一律透過 Member.can()/limit()。
"""
from dataclasses import dataclass
from enum import Enum


class FeatureKind(str, Enum):
    BOOL = "bool"    # 0=鎖定, 非0=開放 -> Member.can()
    QUOTA = "quota"  # -1=無限, 0=停用, 正數=上限 -> Member.limit()


class FeatureStatus(str, Enum):
    ACTIVE = "active"              # 目前有程式碼讀取
    UNREFERENCED = "unreferenced"  # 存在於 DB limits JSON，但查無讀取端（2026-07-30 稽核）


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    kind: FeatureKind
    default: int      # tier.limits 缺這個 key 時，Member.can()/limit() 回傳的值
    label: str         # admin 表單欄位標籤
    description: str   # admin 表單 help text
    status: FeatureStatus = FeatureStatus.ACTIVE


FEATURES: dict[str, FeatureSpec] = {
    # ── 目前有程式碼讀取 ──
    "script": FeatureSpec(
        "script", FeatureKind.BOOL, default=0,
        label="Script 檢視",
        description="Edition 詳情頁 GM 講稿內容檢視權限",
    ),
    "flowchart_print": FeatureSpec(
        "flowchart_print", FeatureKind.BOOL, default=0,
        label="流程圖列印",
        description="流程圖列印/匯出功能",
    ),
    "flowchart_fullscreen": FeatureSpec(
        "flowchart_fullscreen", FeatureKind.BOOL, default=0,
        label="流程圖全螢幕瀏覽",
        description="流程圖全螢幕檢視功能",
    ),
    "flowchart_tour": FeatureSpec(
        "flowchart_tour", FeatureKind.BOOL, default=0,
        label="流程圖步驟導覽",
        description="流程圖互動式逐步導覽（新視窗）功能",
    ),
    "flowchart_non_initial": FeatureSpec(
        "flowchart_non_initial", FeatureKind.BOOL, default=0,
        label="瀏覽非入門流程圖",
        description="Edition 詳情頁流程圖分頁：可看 RulebookFlowchart.initial=False "
                     "（非入門圖，例如各種變體規則）的內容。鎖住時只看得到 ruleset "
                     "名稱與付費牆，圖本身不進頁面原始碼",
    ),
    "edition_unlock": FeatureSpec(
        "edition_unlock", FeatureKind.QUOTA, default=3,
        label="免費永久解鎖 Edition 名額",
        description="會員可免費自選幾款 edition 永久解鎖（流程圖全螢幕／列印／步驟導覽、"
                     "非入門 ruleset，以及該 edition 的 Rulesbot 無限查問）。"
                     "-1=無限, 0=停用, 正數=名額數。只計 EditionUnlock.source='free'；"
                     "US$1 單品加購不受此限。名額選定後不可變更（除非該 edition 尚無已發布"
                     "流程圖），且不隨 tier 降級失效——權益一旦兌換就不再看 tier",
    ),
    "prompt_per_week": FeatureSpec(
        "prompt_per_week", FeatureKind.QUOTA, default=-1,
        label="每週 AI 對話次數上限",
        description="-1=無限, 0=停用, 正數=每週上限（此 key 缺席時預設無限，"
                     "為既有行為的明確記錄，非意外）",
    ),
    "max_bookmark_category": FeatureSpec(
        "max_bookmark_category", FeatureKind.QUOTA, default=0,
        label="收藏分類上限",
        description="-1=無限, 0=不可建立新分類（收藏一律進系統預設分類）, 正數=可建立的分類數上限",
    ),

    # ── 2026-07-30 稽核：tjweb / tjapp 皆查無程式碼讀取，刪除前請先確認 ──
    "flowchart_translate": FeatureSpec(
        "flowchart_translate", FeatureKind.BOOL, default=0,
        label="(未使用?) 流程圖翻譯",
        description="⚠️ 2026-08-15 起流程圖一律自動在地化成介面語言、不再有付費翻譯按鈕，"
                     "此 key 查無程式碼讀取，刪除前請先確認",
        status=FeatureStatus.UNREFERENCED,
    ),
    "weight": FeatureSpec(
        "weight", FeatureKind.QUOTA, default=0,
        label="(未使用?) Weight",
        description="⚠️ 目前查無程式碼讀取此 key，刪除前請先確認",
        status=FeatureStatus.UNREFERENCED,
    ),
    "hide_ad": FeatureSpec(
        "hide_ad", FeatureKind.BOOL, default=0,
        label="(未使用?) 隱藏廣告",
        description="⚠️ 目前查無程式碼讀取此 key，刪除前請先確認",
        status=FeatureStatus.UNREFERENCED,
    ),
    "can_share": FeatureSpec(
        "can_share", FeatureKind.BOOL, default=0,
        label="(未使用?) 分享功能",
        description="⚠️ 目前查無程式碼讀取此 key，刪除前請先確認",
        status=FeatureStatus.UNREFERENCED,
    ),
    "save_settings": FeatureSpec(
        "save_settings", FeatureKind.BOOL, default=0,
        label="(未使用?) 儲存設定",
        description="⚠️ 目前查無程式碼讀取此 key，刪除前請先確認",
        status=FeatureStatus.UNREFERENCED,
    ),
    "can_recommend_rss": FeatureSpec(
        "can_recommend_rss", FeatureKind.BOOL, default=0,
        label="(未使用?) RSS 推薦",
        description="⚠️ 目前查無程式碼讀取此 key，刪除前請先確認",
        status=FeatureStatus.UNREFERENCED,
    ),
    "can_report_irrelevant_feed": FeatureSpec(
        "can_report_irrelevant_feed", FeatureKind.BOOL, default=0,
        label="(未使用?) 檢舉不相關動態",
        description="⚠️ 目前查無程式碼讀取此 key，刪除前請先確認",
        status=FeatureStatus.UNREFERENCED,
    ),
}


def get_spec(key: str) -> FeatureSpec | None:
    return FEATURES.get(key)
