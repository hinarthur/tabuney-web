"""首頁「From the tabletop world」文章區與底部「Ready to play?」CTA 的字串。"""

from django.db import migrations

STRINGS = {
    'home.world.title': {
        'en': 'From the tabletop world',
        'zh': '來自桌遊世界',
        'ja': 'テーブルトップの世界から',
        'de': 'Aus der Brettspielwelt',
        'fr': 'Du monde du jeu de société',
        'es': 'Del mundo de los juegos de mesa',
    },
    'home.world.subtitle': {
        'en': 'News, reviews and stories from the board game community.',
        'zh': '來自桌遊社群的新聞、評測與故事。',
        'ja': 'ボードゲームコミュニティからのニュース、レビュー、ストーリー。',
        'de': 'Neuigkeiten, Rezensionen und Geschichten aus der Brettspiel-Community.',
        'fr': 'Actualités, critiques et histoires de la communauté du jeu de société.',
        'es': 'Noticias, reseñas e historias de la comunidad de juegos de mesa.',
    },
    'home.world.more': {
        'en': 'Read more articles',
        'zh': '閱讀更多文章',
        'ja': 'さらに記事を読む',
        'de': 'Weitere Artikel lesen',
        'fr': 'Lire plus d’articles',
        'es': 'Leer más artículos',
    },
    'home.cta.title': {
        'en': 'Ready to play?',
        'zh': '準備開玩了嗎？',
        'ja': 'さあ、遊びましょう',
        'de': 'Bereit zu spielen?',
        'fr': 'Prêt à jouer ?',
        'es': '¿Listo para jugar?',
    },
    'home.cta.desc': {
        'en': 'Find a game, explore its guide, and get to the table.',
        'zh': '找到遊戲、看懂攻略，然後上桌開玩。',
        'ja': 'ゲームを見つけて、ガイドを読んで、テーブルへ。',
        'de': 'Finde ein Spiel, entdecke die Anleitung und setz dich an den Tisch.',
        'fr': 'Trouvez un jeu, parcourez son guide et mettez-vous à table.',
        'es': 'Encuentra un juego, explora su guía y siéntate a la mesa.',
    },
    'home.cta.note': {
        'en': 'Good games bring people together.',
        'zh': '好遊戲，讓人聚在一起。',
        'ja': '良いゲームは、人をつなぐ。',
        'de': 'Gute Spiele bringen Menschen zusammen.',
        'fr': 'Les bons jeux rapprochent les gens.',
        'es': 'Los buenos juegos unen a las personas.',
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
        ('translation', '0044_home_overview_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
