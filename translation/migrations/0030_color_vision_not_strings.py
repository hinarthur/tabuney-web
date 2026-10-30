"""
色覺友善新增 False 狀態（需辨色）的圖示，補上它的名稱與圖例說明。

True 用的 game.label.color_vision_friendly / .def 在 0029 已建立，這裡不動。
"""

from django.db import migrations

STRINGS = {
    'game.label.color_vision_friendly.no': {
        'en': 'Relies on Color',
        'zh': '需辨色',
        'ja': '色の識別が必要',
        'de': 'Farbabhängig',
        'fr': 'Dépend de la couleur',
        'es': 'Depende del color',
    },
    'game.label.color_vision_friendly.no.def': {
        'en': (
            'Some components can only be told apart by color — no shape, symbol or pattern '
            'carries the same information, so players with color vision deficiency may need '
            'help or a house rule.'
        ),
        'zh': '部分元件只能靠顏色區分，沒有形狀、符號或紋路可替代，色盲／色弱玩家可能需要他人協助或自訂規則。',
        'ja': '一部のコンポーネントは色でしか区別できず、形・記号・模様による代替がないため、色覚特性のあるプレイヤーは支援やハウスルールが必要になる場合があります。',
        'de': (
            'Manche Komponenten lassen sich nur über die Farbe unterscheiden — keine Form, kein '
            'Symbol und kein Muster trägt dieselbe Information, sodass Spielende mit Farbsehschwäche '
            'Hilfe oder eine Hausregel brauchen können.'
        ),
        'fr': (
            'Certains éléments ne se distinguent que par la couleur : aucune forme, symbole ou motif '
            'ne porte la même information, si bien que les joueurs daltoniens peuvent avoir besoin '
            "d'aide ou d'une règle maison."
        ),
        'es': (
            'Algunos componentes solo se distinguen por el color: ninguna forma, símbolo o patrón '
            'aporta la misma información, por lo que quienes tienen daltonismo pueden necesitar '
            'ayuda o una regla de la casa.'
        ),
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
        ('translation', '0029_color_vision_friendly_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
