"""
seo.default.title 只是 <title>/og:title 沒被個別頁面覆寫時的 fallback——目前幾乎
所有真實頁面都自己覆寫了 title（首頁、搜尋、遊戲詳細頁、Feed、about/terms/privacy
等），這個 fallback 極少真的顯示出來，不需要六語言各自的行銷文案，直接統一顯示
網站名稱即可。

seo.default.description 不動：它仍是多個頁面（about/terms/privacy 等）實際會用到
的說明文字，需要保留各語言翻譯。
"""

from django.db import migrations

NEW_TITLE = 'Tabuney'

# 對應 0008_seo_default_strings.py 原本的 title 值，供 reverse 還原
OLD_TITLES = {
    'en': 'Tabuney — Board game rules, setup guides and GM scripts',
    'zh': 'Tabuney — 桌遊規則、開場設置與主持人講稿',
    'ja': 'Tabuney — ボードゲームのルール・セットアップ・GM台本',
    'de': 'Tabuney — Brettspielregeln, Aufbau-Anleitungen und Spielleiter-Skripte',
    'fr': 'Tabuney — Règles de jeux de société, mise en place et scripts de meneur',
    'es': 'Tabuney — Reglas de juegos de mesa, preparación y guiones de director',
}


def _set_title(apps, values_by_lang):
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    for lang, value in values_by_lang.items():
        tribe = Tribe.objects.filter(language=lang).first()
        if tribe is None:
            continue
        Translation.objects.update_or_create(
            tribe=tribe, key='seo.default.title',
            defaults={'value': value, 'is_synced': False},
        )


def simplify_title(apps, schema_editor):
    _set_title(apps, {lang: NEW_TITLE for lang in OLD_TITLES})


def restore_title(apps, schema_editor):
    _set_title(apps, OLD_TITLES)


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0010_seo_games_feed_descriptions'),
    ]

    operations = [
        migrations.RunPython(simplify_title, restore_title),
    ]
