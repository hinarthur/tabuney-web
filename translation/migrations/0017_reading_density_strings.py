"""
edition_detail 的 info-section 新增「文字量」(reading density) 屬性，
補上屬性名稱與四個值的翻譯字串。
"""

from django.db import migrations

STRINGS = {
    'game.label.reading_density': {
        'en': 'Reading Density',
        'zh': '文字量',
        'ja': '文字量',
        'de': 'Lesedichte',
        'fr': 'Densité de texte',
        'es': 'Densidad de texto',
    },
    'game.reading_density.none': {
        'en': 'None',
        'zh': '無文字',
        'ja': 'なし',
        'de': 'Keine',
        'fr': 'Aucun',
        'es': 'Ninguno',
    },
    'game.reading_density.labels': {
        'en': 'Labels',
        'zh': '僅標籤',
        'ja': '単語のみ',
        'de': 'Beschriftungen',
        'fr': 'Étiquettes',
        'es': 'Etiquetas',
    },
    'game.reading_density.simple': {
        'en': 'Simple',
        'zh': '簡單句',
        'ja': '簡単な文',
        'de': 'Einfach',
        'fr': 'Simple',
        'es': 'Sencillo',
    },
    'game.reading_density.complex': {
        'en': 'Complex',
        'zh': '複雜文本',
        'ja': '複雑な文',
        'de': 'Komplex',
        'fr': 'Complexe',
        'es': 'Complejo',
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
        ('translation', '0016_faq_categories'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
