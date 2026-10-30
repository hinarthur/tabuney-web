"""
base.html 的預設 <title> 與 meta description。

原本 base.html 的預設 title 是字面上的 "My Title"，任何沒有覆寫 title 區塊的頁面
都會用它。改成翻譯 key 之後，這些字串必須存在，否則會渲染成 "seo.default.title"。

用 data migration 而非後台手輸，是為了讓本地與 VPS 兩個資料庫必然一致。
"""

from django.db import migrations

SEO_STRINGS = {
    'en': {
        'seo.default.title': 'Tabuney — Board game rules, setup guides and GM scripts',
        'seo.default.description': (
            'Look up any board game: player count, playtime, setup, rules Q&A, '
            'flowcharts and ready-to-read game master scripts.'
        ),
    },
    'zh': {
        'seo.default.title': 'Tabuney — 桌遊規則、開場設置與主持人講稿',
        'seo.default.description': (
            '查詢任何桌遊：人數、遊玩時間、開場設置、規則問答、流程圖，'
            '以及可直接照著唸的主持人講稿。'
        ),
    },
    'ja': {
        'seo.default.title': 'Tabuney — ボードゲームのルール・セットアップ・GM台本',
        'seo.default.description': (
            'ボードゲームを検索：人数、プレイ時間、セットアップ、ルールQ&A、'
            'フローチャート、そのまま読めるゲームマスター台本。'
        ),
    },
    'de': {
        'seo.default.title': 'Tabuney — Brettspielregeln, Aufbau-Anleitungen und Spielleiter-Skripte',
        'seo.default.description': (
            'Schlage jedes Brettspiel nach: Spielerzahl, Spieldauer, Aufbau, '
            'Regelfragen, Flussdiagramme und fertige Spielleiter-Skripte.'
        ),
    },
    'fr': {
        'seo.default.title': 'Tabuney — Règles de jeux de société, mise en place et scripts de meneur',
        'seo.default.description': (
            'Consultez n\'importe quel jeu de société : nombre de joueurs, durée, '
            'mise en place, questions de règles, organigrammes et scripts de meneur prêts à lire.'
        ),
    },
    'es': {
        'seo.default.title': 'Tabuney — Reglas de juegos de mesa, preparación y guiones de director',
        'seo.default.description': (
            'Consulta cualquier juego de mesa: número de jugadores, duración, '
            'preparación, dudas de reglas, diagramas de flujo y guiones listos para leer.'
        ),
    },
}


def add_seo_strings(apps, schema_editor):
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    for lang, entries in SEO_STRINGS.items():
        tribe = Tribe.objects.filter(language=lang).first()
        if tribe is None:
            continue
        for key, value in entries.items():
            Translation.objects.update_or_create(
                tribe=tribe, key=key, defaults={'value': value, 'is_synced': False},
            )


def remove_seo_strings(apps, schema_editor):
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(key__in=['seo.default.title', 'seo.default.description']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0007_translation_is_synced_translation_synced_at'),
    ]

    operations = [
        migrations.RunPython(add_seo_strings, remove_seo_strings),
    ]
