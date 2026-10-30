"""
game_search.html（首頁 / 與 /games/ 共用的 view）與 feed_list.html 先前都沒有
自己的 meta description，跟其他頁面共用 seo.default.description，構成
Search Console 會標記的「重複 meta description」。這裡補上各自專屬的文案。
"""

from django.db import migrations

STRINGS = {
    'seo.games.description': {
        'en': 'Search and browse board games by player count, playtime and complexity. '
              'See setup guides, rules Q&A and flowcharts for each game.',
        'zh': '依人數、時間、複雜度搜尋與瀏覽桌遊，查看每款遊戲的開場設置、規則問答與流程圖。',
        'ja': 'プレイ人数・時間・複雑さでボードゲームを検索。各ゲームのセットアップ、'
              'ルールQ&A、フローチャートを確認できます。',
        'de': 'Durchsuche Brettspiele nach Spielerzahl, Spieldauer und Komplexität. '
              'Sieh dir Aufbau-Anleitungen, Regelfragen und Flussdiagramme für jedes Spiel an.',
        'fr': 'Recherchez des jeux de société par nombre de joueurs, durée et complexité. '
              'Consultez la mise en place, les questions de règles et les organigrammes de chaque jeu.',
        'es': 'Busca juegos de mesa por número de jugadores, duración y complejidad. '
              'Consulta la preparación, dudas de reglas y diagramas de flujo de cada juego.',
    },
    'seo.feed.description': {
        'en': 'The latest board game news, reviews and articles, curated and updated daily.',
        'zh': '每日更新的桌遊新聞、評測與文章精選。',
        'ja': '最新のボードゲームニュース・レビュー・記事を毎日更新。',
        'de': 'Die neuesten Brettspiel-News, Rezensionen und Artikel, täglich aktualisiert.',
        'fr': 'Les dernières actualités, critiques et articles sur les jeux de société, mis à jour chaque jour.',
        'es': 'Las últimas noticias, reseñas y artículos sobre juegos de mesa, actualizados a diario.',
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
        ('translation', '0009_membership_script_row'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
