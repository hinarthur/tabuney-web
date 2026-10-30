"""
翻譯 key 使用狀態掃描。

掃整個 repo 找出實際被引用到的 translation key，供 admin 的「掃描使用狀態」
action 使用，判斷哪些 key 已經是孤兒可以清掉。純檔案系統掃描，跟 HTTP 請求
無關，故意不掛在任何 view/list render 上——掃全部 template + .py 檔案不便宜，
只在 admin 手動觸發時才跑。
"""
import re
from pathlib import Path
from django.conf import settings
from django.utils import timezone

# 全站已知的兩處動態組 key，grep 抓不到字面字串，一律視為已使用。
# 稽核紀錄見 migrations/0021_remove_app_only_strings.py 的 docstring。
KNOWN_DYNAMIC_PREFIXES = ("membership.tier.", "chat.opening.")

_EXCLUDED_DIR_NAMES = {
    "migrations", "__pycache__", "static", "staticfiles", "media",
    "qdrant_storage", "temp", "node_modules", ".git",
}

# 樣板裡永遠透過 `{% t "key" %}` 這個固定語法取字串（translate_tags.py:t()），
# 所以模板端直接鎖定這個 tag 語法即可，不管 key 長怎樣（有沒有點、大小寫）都準確
# 抓得到，例如 "faq.title" 也抓得到 "Profile"、"cancel" 這種單詞 key。
_TAG_KEY_RE = re.compile(r"""\{%\s*t\s+['"]([^'"]+)['"]""")

# Python 端沒有固定呼叫語法可鎖（selectors.get_translation 之外，還有
# game/views/suggestion_views.py 的 `_t(request, key, default)` 這種在地包裝，
# 未來還可能再冒出別的包裝函式名）。退而求其次：整份 .py 檔只要出現「長得像
# key」的字面字串（多段小寫英數/底線/連字號用點分隔，如
# "game.suggest.error.name-required"）就算用到。目前 repo 裡所有 Python 端會
# 直接傳字面 key 的呼叫都是這種點分格式（selectors.py、context_processors.py、
# suggestion_views.py 皆是），沒有單詞 key 只在 Python 端出現的案例。
_DOTTED_KEY_LITERAL_RE = re.compile(r"""['"]([a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+)['"]""")


def _iter_files(root: Path, suffix: str):
    for path in root.rglob(f"*{suffix}"):
        if any(part in _EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        yield path


def scan_used_keys() -> set:
    """回傳目前程式碼裡看起來有被引用到的 translation key 字面字串集合。"""
    base_dir = Path(settings.BASE_DIR)
    used = set()

    for path in _iter_files(base_dir, ".html"):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        used.update(_TAG_KEY_RE.findall(text))

    for path in _iter_files(base_dir, ".py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        used.update(_DOTTED_KEY_LITERAL_RE.findall(text))

    return used


def apply_usage_scan():
    """掃描一次，把結果寫回所有 Translation 列，回傳 (used_count, unused_count)。"""
    from .models import Translation

    used_keys = scan_used_keys()
    now = timezone.now()

    all_keys = set(Translation.objects.values_list("key", flat=True).distinct())
    confirmed_used = {
        k for k in all_keys
        if k in used_keys or k.startswith(KNOWN_DYNAMIC_PREFIXES)
    }
    confirmed_unused = all_keys - confirmed_used

    used_count = Translation.objects.filter(key__in=confirmed_used).update(
        is_used=True, used_checked_at=now
    )
    unused_count = Translation.objects.filter(key__in=confirmed_unused).update(
        is_used=False, used_checked_at=now
    )
    return used_count, unused_count
