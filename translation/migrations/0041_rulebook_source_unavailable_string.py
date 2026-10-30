"""
書本按鈕的灰色狀態（連結失效／沒有外部出處）合併成同一句 tooltip，
取代 0040 的 .broken / .missing 兩個 key。
"""

from django.db import migrations

OLD_KEYS = ['game.rulebook.source.broken', 'game.rulebook.source.missing']

STRINGS = {
    'game.rulebook.source.unavailable': {
        'en': 'No external source available for this rulebook',
        'zh': '此規則書沒有可用的外部出處',
        'ja': 'このルールブックには利用できる外部の出典がありません',
        'de': 'Für dieses Regelheft ist keine externe Quelle verfügbar',
        'fr': "Aucune source externe disponible pour ce livret de règles",
        'es': 'No hay una fuente externa disponible para este reglamento',
    },
}


def add_strings(apps, schema_editor):
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    Translation.objects.filter(key__in=OLD_KEYS).delete()
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
        ('translation', '0040_rulebook_source_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
