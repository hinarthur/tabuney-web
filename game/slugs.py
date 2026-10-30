"""
Edition 的 SEO 網址 slug 產生邏輯。

slug 形式為 `<標題>-<發行年>`，例如 `catan-2nd-edition-2019`、`卡坦島-2019`。

兩個刻意的設計決定：

1. `allow_unicode=True` — Edition.name 實務上存的是在地化標題（見 game/admin.py 的
   `alternate_name or name`），中日文佔大宗。ASCII slugify 會把它們變成空字串，
   那樣幾乎每個中日文 edition 都會退化成純 UUID 網址。

2. 撞名時用 UUID 前綴而非 `-2`/`-3` 計數器 — 本地與 VPS 是兩個獨立資料庫，
   插入順序不同，計數器會讓同一個 edition 在兩邊算出不同 slug。
   UUID 前綴是該列的純函數，兩邊必然一致。
"""

from django.utils.text import slugify

# ASCII 結果短於這個長度就視為「被砍太兇」，改用 unicode 版本。
# 例如「島 A」的 ASCII 結果是 "a"，顯然不該拿來當網址。
_MIN_ASCII_LEN = 3


def slugify_title(raw: str) -> str:
    """
    優先產出 ASCII slug，必要時才保留 unicode。

    拉丁變音符號（café、fürstenfeld）轉成 ASCII 比較乾淨 —— unicode slug 在
    連結裡會變成 caf%C3%A9-... 這種樣子。但中日文標題經 ASCII slugify 會變成
    空字串，那種情況就必須保留 unicode。
    """
    raw = (raw or "").strip()
    ascii_slug = slugify(raw)
    if len(ascii_slug) >= _MIN_ASCII_LEN:
        return ascii_slug

    unicode_slug = slugify(raw, allow_unicode=True)
    if len(unicode_slug) > len(ascii_slug):
        return unicode_slug
    return ascii_slug


def build_edition_slug_base(edition) -> str:
    """算出 slug 的基底（未處理唯一性）。"""
    raw = (edition.name or "").strip()
    if not raw and edition.game_id:
        raw = (edition.game.canonical_name or "").strip()

    base = slugify_title(raw) or "edition"

    if edition.release_year:
        base = f"{base}-{edition.release_year}"
    return base[:200]


def build_unique_edition_slug(edition) -> str:
    """算出一個在 Edition.slug 與 EditionSlugAlias.slug 之間都唯一的 slug。"""
    from game.models import Edition, EditionSlugAlias

    base = build_edition_slug_base(edition)

    def taken(candidate):
        if Edition.objects.filter(slug=candidate).exclude(pk=edition.pk).exists():
            return True
        return EditionSlugAlias.objects.filter(slug=candidate).exclude(
            edition_id=edition.pk
        ).exists()

    if not taken(base):
        return base

    candidate = f"{base}-{str(edition.pk)[:6]}"[:220]
    if not taken(candidate):
        return candidate

    return f"{base}-{edition.pk}"[:220]
