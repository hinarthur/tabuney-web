"""
回填既有 Edition 的 slug。

必須是 data migration 而非 management command：deploy.yml 會在容器切換「之前」
自動跑 migrate。若改用指令，從容器切換到人工執行指令之間，每個呼叫
get_absolute_url() 的頁面都會吐出 /games/None/。

helper 邏輯是 game/slugs.py 的複本而非 import —— data migration 必須凍結，
不能隨日後 game/slugs.py 的改動而改變歷史行為。
"""

from django.db import migrations
from django.utils.text import slugify


_MIN_ASCII_LEN = 3


def _slugify_title(raw):
    raw = (raw or "").strip()
    ascii_slug = slugify(raw)
    if len(ascii_slug) >= _MIN_ASCII_LEN:
        return ascii_slug
    unicode_slug = slugify(raw, allow_unicode=True)
    return unicode_slug if len(unicode_slug) > len(ascii_slug) else ascii_slug


def _slug_base(name, canonical_name, release_year):
    raw = (name or "").strip() or (canonical_name or "").strip()
    base = _slugify_title(raw) or "edition"
    if release_year:
        base = f"{base}-{release_year}"
    return base[:200]


def backfill(apps, schema_editor):
    Edition = apps.get_model("game", "Edition")

    editions = list(
        Edition.objects.select_related("game")
        .only("id", "name", "release_year", "slug", "game__canonical_name")
        .order_by("id")
    )
    if not editions:
        return

    # 在記憶體裡解衝突，避免每列一次 EXISTS 查詢
    taken = set()
    to_update = []

    for edition in editions:
        if edition.slug:
            taken.add(edition.slug)
            continue

        canonical = edition.game.canonical_name if edition.game_id else ""
        base = _slug_base(edition.name, canonical, edition.release_year)

        candidate = base
        if candidate in taken:
            candidate = f"{base}-{str(edition.id)[:6]}"[:220]
        if candidate in taken:
            candidate = f"{base}-{edition.id}"[:220]

        taken.add(candidate)
        edition.slug = candidate
        to_update.append(edition)

    for i in range(0, len(to_update), 500):
        Edition.objects.bulk_update(to_update[i:i + 500], ["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0105_edition_slug_and_alias"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
