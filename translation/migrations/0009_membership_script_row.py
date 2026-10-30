"""
membership.html 新增了「GM 講稿檢視」那一列（對應後端 script feature），
需要 membership.script.view 這個翻譯 key，六語言都補上。
"""

from django.db import migrations

STRINGS = {
    'en': 'GM Script Access',
    'zh': 'GM 講稿檢視',
    'ja': 'GMスクリプト閲覧',
    'de': 'Zugriff auf GM-Skript',
    'fr': 'Accès au script du MJ',
    'es': 'Acceso al guion del DJ',
}


def add_string(apps, schema_editor):
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    for lang, value in STRINGS.items():
        tribe = Tribe.objects.filter(language=lang).first()
        if tribe is None:
            continue
        Translation.objects.update_or_create(
            tribe=tribe, key='membership.script.view',
            defaults={'value': value, 'is_synced': False},
        )


def remove_string(apps, schema_editor):
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(key='membership.script.view').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0008_seo_default_strings'),
    ]

    operations = [
        migrations.RunPython(add_string, remove_string),
    ]
