"""
Rulesbot / Flowchart 分頁工具列新增書本按鈕，連到規則書出處（Rulebook.source_url）。
這裡是按鈕 tooltip 的 UI 字串。
"""

from django.db import migrations

STRINGS = {
    'game.rulebook.source': {
        'en': 'View the rulebook source',
        'zh': '查看規則書出處',
        'ja': 'ルールブックの出典を見る',
        'de': 'Quelle des Regelhefts ansehen',
        'fr': 'Voir la source du livret de règles',
        'es': 'Ver la fuente del reglamento',
    },
    'game.rulebook.source.broken': {
        'en': 'The original source is no longer available',
        'zh': '原出處已失效',
        'ja': '元の出典は現在利用できません',
        'de': 'Die ursprüngliche Quelle ist nicht mehr verfügbar',
        'fr': "La source d'origine n'est plus disponible",
        'es': 'La fuente original ya no está disponible',
    },
    'game.rulebook.source.missing': {
        'en': 'No external source for this rulebook',
        'zh': '此規則書沒有外部出處',
        'ja': 'このルールブックには外部の出典がありません',
        'de': 'Für dieses Regelheft gibt es keine externe Quelle',
        'fr': "Ce livret de règles n'a pas de source externe",
        'es': 'Este reglamento no tiene una fuente externa',
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
        ('translation', '0039_unlock_return_pending_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
