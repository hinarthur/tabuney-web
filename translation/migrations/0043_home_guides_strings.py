"""首頁「Popular gameplay guides」區塊（隨機流程圖遊戲卡＋搜尋入口）的字串。"""

from django.db import migrations

STRINGS = {
    'home.guides.title': {
        'en': 'Popular gameplay guides',
        'zh': '熱門遊戲攻略',
        'ja': '人気のプレイガイド',
        'de': 'Beliebte Spielanleitungen',
        'fr': 'Guides de jeu populaires',
        'es': 'Guías de juego populares',
    },
    'home.guides.subtitle': {
        'en': 'Explore flowcharts for some of the most loved board games.',
        'zh': '看看幾款人氣桌遊的規則流程圖。',
        'ja': '人気ボードゲームのフローチャートをチェック。',
        'de': 'Entdecke Flussdiagramme zu beliebten Brettspielen.',
        'fr': 'Découvrez les organigrammes de jeux de société très appréciés.',
        'es': 'Explora los diagramas de flujo de algunos de los juegos de mesa más queridos.',
    },
    'home.guides.browse_all': {
        'en': 'Browse all games',
        'zh': '瀏覽所有遊戲',
        'ja': 'すべてのゲームを見る',
        'de': 'Alle Spiele ansehen',
        'fr': 'Parcourir tous les jeux',
        'es': 'Ver todos los juegos',
    },
    'home.guides.find_title': {
        'en': 'Find your game',
        'zh': '找到你的遊戲',
        'ja': 'ゲームを探す',
        'de': 'Finde dein Spiel',
        'fr': 'Trouvez votre jeu',
        'es': 'Encuentra tu juego',
    },
    'home.guides.find_desc': {
        'en': 'Search hundreds of games and growing.',
        'zh': '搜尋數百款遊戲，持續增加中。',
        'ja': '数百のゲームを検索できます。さらに増加中。',
        'de': 'Durchsuche Hunderte Spiele – und es werden mehr.',
        'fr': 'Cherchez parmi des centaines de jeux, et ça continue.',
        'es': 'Busca entre cientos de juegos, y sigue creciendo.',
    },
    'home.guides.find_button': {
        'en': 'Search games',
        'zh': '搜尋遊戲',
        'ja': 'ゲームを検索',
        'de': 'Spiele suchen',
        'fr': 'Chercher des jeux',
        'es': 'Buscar juegos',
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
        ('translation', '0042_home_hero_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
