"""
Edition 新增「色覺友善」(color vision friendly) 屬性，
補上屬性名稱與圖例說明的翻譯字串。
"""

from django.db import migrations

STRINGS = {
    'game.label.color_vision_friendly': {
        'en': 'Color Vision Friendly',
        'zh': '色覺友善',
        'ja': '色覚サポート',
        'de': 'Farbsehen-freundlich',
        'fr': 'Adapté au daltonisme',
        'es': 'Apto para daltonismo',
    },
    'game.label.color_vision_friendly.def': {
        'en': (
            'Components can be told apart without relying on color alone — shapes, symbols '
            'or patterns carry the same information, so players with color vision deficiency '
            'can play unaided.'
        ),
        'zh': '元件不只靠顏色區分，形狀、符號或紋路也帶有同樣資訊，色盲／色弱玩家不需他人協助即可辨識。',
        'ja': 'コンポーネントは色だけに頼らず、形・記号・模様でも同じ情報が伝わるため、色覚特性のあるプレイヤーも支援なしで遊べます。',
        'de': (
            'Die Komponenten lassen sich ohne Farbe allein unterscheiden — Formen, Symbole oder '
            'Muster tragen dieselbe Information, sodass Spielende mit Farbsehschwäche ohne Hilfe '
            'spielen können.'
        ),
        'fr': (
            'Les éléments se distinguent sans dépendre uniquement de la couleur : formes, symboles '
            'ou motifs portent la même information, permettant aux joueurs daltoniens de jouer sans '
            'aide extérieure.'
        ),
        'es': (
            'Los componentes se distinguen sin depender solo del color: formas, símbolos o patrones '
            'aportan la misma información, de modo que quienes tienen daltonismo pueden jugar sin '
            'ayuda.'
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
        ('translation', '0028_flowchart_suggest_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
