"""
seo.game.search.title 與 seo.feed.list.title 一直只存在於正式站 DB，沒有任何
migration seed 過，新環境撈不到就會 fallback 回 key 本身（translate_tags.t）。

這兩個 key 原本只出現在 <title>，缺了頂多標題怪；現在 game_search.html 與
feed_list.html 的 <h1> 也改用同一個 key（title 與 h1 要對齊），缺值會直接在
頁面正中央印出 "seo.game.search.title" 這行字。這裡補上 seed。

值取自正式站現有內容，不是新翻的。
"""

from django.db import migrations

STRINGS = {
    'seo.game.search.title': {
        'en': 'Instant Tabletop Game Guides',
        'zh': '即時桌遊指南',
        'ja': 'すぐに使えるテーブルゲームガイド',
        'de': 'Sofort verfügbare Tabletop-Spielhilfen',
        'fr': 'Guides instantanés de jeux de société',
        'es': 'Guías instantáneas para juegos de mesa',
    },
    'seo.feed.list.title': {
        'en': 'Tabletop Game News Feed',
        'zh': '桌遊新聞動態',
        'ja': 'テーブルゲームニュースフィード',
        'de': 'Tabletop-Spiele-Newsfeed',
        'fr': 'Fil d’actualités des jeux de société',
        'es': 'Noticias de juegos de mesa',
    },
}


def add_strings(apps, schema_editor):
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    for key, translations in STRINGS.items():
        for lang, value in translations.items():
            tribe = Tribe.objects.filter(language=lang).first()
            if tribe is None:
                continue
            Translation.objects.update_or_create(
                tribe=tribe, key=key,
                defaults={'value': value, 'is_synced': False},
            )


def remove_strings(apps, schema_editor):
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(key__in=list(STRINGS.keys())).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0019_membership_promo_i18n'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
