"""
Flowchart 分頁新增文字版（<details> 折疊區塊，內容與畫面上的圖表一致），給不執行
JS 的爬蟲、螢幕閱讀器與小螢幕使用者讀。這裡是文字版本身用到的三個 UI 字串。
"""

from django.db import migrations

STRINGS = {
    'game.flowchart.textview.title': {
        'en': 'Text version of this flowchart',
        'zh': '流程圖文字版',
        'ja': 'フローチャートのテキスト版',
        'de': 'Textfassung des Flussdiagramms',
        'fr': "Version texte de l'organigramme",
        'es': 'Versión en texto del diagrama',
    },
    'game.flowchart.textview.desc': {
        'en': "The same flow as the chart above, written out step by step — "
              "easier to read on small screens, with screen readers, or when "
              "the chart doesn't load.",
        'zh': '和上方流程圖完全相同的內容，逐步寫成文字 —— 小螢幕、螢幕閱讀器，或圖表載入不出來時比較好讀。',
        'ja': '上のフローチャートと同じ内容をステップごとに文章化したものです。'
              '小さい画面やスクリーンリーダー、図が読み込めない場合に読みやすくなります。',
        'de': 'Derselbe Ablauf wie im Diagramm oben, Schritt für Schritt als Text — '
              'besser lesbar auf kleinen Bildschirmen, mit Screenreadern oder wenn '
              'das Diagramm nicht lädt.',
        'fr': "Le même déroulement que le schéma ci-dessus, écrit étape par étape "
              "— plus facile à lire sur petit écran, avec un lecteur d'écran, ou "
              "si le schéma ne se charge pas.",
        'es': 'El mismo flujo que el diagrama de arriba, escrito paso a paso: más '
              'fácil de leer en pantallas pequeñas, con lectores de pantalla, o '
              'cuando el diagrama no carga.',
    },
    'game.flowchart.textview.legends': {
        'en': 'Additional notes',
        'zh': '補充說明',
        'ja': '補足説明',
        'de': 'Zusätzliche Hinweise',
        'fr': 'Notes complémentaires',
        'es': 'Notas adicionales',
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
        ('translation', '0025_flowchart_tour_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
