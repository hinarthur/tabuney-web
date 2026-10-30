"""
membership.html 新增四列比較項目：素養指標瀏覽、收藏狀態記錄、桌遊偏好記錄、
新聞瀏覽，需要對應的翻譯 key，六語言都補上。
"""

from django.db import migrations

STRINGS = {
    'membership.platvm.view': {
        'en': 'Browse Game Skill Indicators',
        'zh': '瀏覽桌遊的素養指標',
        'ja': 'ボードゲームのスキル指標を閲覧',
        'de': 'Spielkompetenz-Indikatoren durchsuchen',
        'fr': 'Parcourir les indicateurs de compétences du jeu',
        'es': 'Explorar los indicadores de habilidades del juego',
    },
    'membership.collection.save': {
        'en': 'Save Collection Status',
        'zh': '記錄收藏狀態',
        'ja': 'コレクション状態を記録',
        'de': 'Sammlungsstatus speichern',
        'fr': "Enregistrer l'état de la collection",
        'es': 'Guardar el estado de la colección',
    },
    'membership.preference.save': {
        'en': 'Save Game Preferences',
        'zh': '記錄桌遊偏好',
        'ja': 'ボードゲームの好みを記録',
        'de': 'Spielpräferenzen speichern',
        'fr': 'Enregistrer les préférences de jeu',
        'es': 'Guardar preferencias de juego',
    },
    'membership.news.browsing': {
        'en': 'Browse News',
        'zh': '瀏覽新聞',
        'ja': 'ニュースを閲覧',
        'de': 'Neuigkeiten durchsuchen',
        'fr': 'Parcourir les actualités',
        'es': 'Explorar noticias',
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
    Translation.objects.filter(key__in=STRINGS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0013_seo_page_descriptions'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
