"""
Flowchart 底部固定顯示一行免責說明（網頁與列印版都會出現），提醒讀者流程圖
只是依規則書整理的參考，正式規則以官方規則書為準。
"""

from django.db import migrations

STRINGS = {
    'game.flowchart.footnote': {
        'en': 'This flowchart is a summary based on the rulebook and is for '
              'reference only — the official rulebook always takes precedence.',
        'zh': '本流程圖依規則書整理，僅供參考；實際規則請以官方規則書為準。',
        'ja': 'このフローチャートはルールブックをもとに整理した参考用です。'
              '実際のルールは公式ルールブックが優先されます。',
        'de': 'Dieses Flussdiagramm ist eine Zusammenfassung des Regelwerks und '
              'dient nur zur Orientierung — maßgeblich ist stets das offizielle Regelwerk.',
        'fr': "Cet organigramme est un résumé établi d'après le livret de règles "
              "et n'est fourni qu'à titre indicatif : les règles officielles font foi.",
        'es': 'Este diagrama es un resumen basado en el reglamento y sirve solo '
              'como referencia; el reglamento oficial siempre prevalece.',
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
        ('translation', '0026_flowchart_textview_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
