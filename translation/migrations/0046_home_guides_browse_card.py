"""
Popular gameplay guides 第 5 張卡改成「Browse」：說明文字與按鈕字更新。
update_or_create 會覆蓋 0043 的舊值，並把 is_synced 設回 False 讓 VPS 同步。
"""

from django.db import migrations

STRINGS = {
    'home.guides.find_desc': {
        'en': 'Explore our growing collection of tabletop games.',
        'zh': '探索我們持續擴充的桌遊收藏。',
        'ja': '増え続けるボードゲームのコレクションを探索しよう。',
        'de': 'Entdecke unsere wachsende Sammlung an Brettspielen.',
        'fr': 'Explorez notre collection de jeux de société en constante croissance.',
        'es': 'Explora nuestra colección de juegos de mesa en constante crecimiento.',
    },
    'home.guides.find_button': {
        'en': 'Browse Games',
        'zh': '瀏覽遊戲',
        'ja': 'ゲームを見る',
        'de': 'Spiele ansehen',
        'fr': 'Parcourir les jeux',
        'es': 'Ver juegos',
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


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0045_home_world_cta_strings'),
    ]

    # 反向不還原舊文案：舊值在 0043，需要的話重跑那支即可
    operations = [
        migrations.RunPython(add_strings, migrations.RunPython.noop),
    ]
