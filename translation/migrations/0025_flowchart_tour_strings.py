"""
edition_detail 流程圖工具列新增 👣 按鈕：開新視窗做互動式逐步導覽（一次聚焦一個
節點、其餘模糊），面板有最頭/上一步/下一步/最尾、decision 節點的分支選項，以及
各 legend 註解的隨點隨看按鈕。
React bundle 沒有 i18n，這些字串由 template 算好後隨 config 傳進導覽視窗。
"""

from django.db import migrations

STRINGS = {
    'game.flowchart.tour': {
        'en': 'Step-by-step tour',
        'zh': '步驟導覽',
        'ja': 'ステップ案内',
        'de': 'Schritt-für-Schritt-Tour',
        'fr': 'Visite pas à pas',
        'es': 'Recorrido paso a paso',
    },
    'game.flowchart.tour.first': {
        'en': 'Back to start',
        'zh': '回到起點',
        'ja': '最初へ戻る',
        'de': 'Zurück zum Anfang',
        'fr': 'Retour au début',
        'es': 'Volver al inicio',
    },
    'game.flowchart.tour.prev': {
        'en': 'Previous step',
        'zh': '上一步',
        'ja': '前のステップ',
        'de': 'Vorheriger Schritt',
        'fr': 'Étape précédente',
        'es': 'Paso anterior',
    },
    'game.flowchart.tour.next': {
        'en': 'Next step',
        'zh': '下一步',
        'ja': '次のステップ',
        'de': 'Nächster Schritt',
        'fr': 'Étape suivante',
        'es': 'Paso siguiente',
    },
    'game.flowchart.tour.last': {
        'en': 'Jump to end',
        'zh': '跳到終點',
        'ja': '最後へ進む',
        'de': 'Zum Ende springen',
        'fr': 'Aller à la fin',
        'es': 'Ir al final',
    },
    'game.flowchart.tour.choose': {
        'en': 'Choose a branch:',
        'zh': '選擇分支：',
        'ja': '分岐を選択：',
        'de': 'Verzweigung wählen:',
        'fr': 'Choisissez une branche :',
        'es': 'Elige una rama:',
    },
    'game.flowchart.tour.notes': {
        'en': 'Notes',
        'zh': '補充說明',
        'ja': '補足説明',
        'de': 'Hinweise',
        'fr': 'Remarques',
        'es': 'Notas',
    },
    'game.flowchart.tour.branch_unnamed': {
        'en': '(unnamed branch)',
        'zh': '（未命名分支）',
        'ja': '（名称のない分岐）',
        'de': '(unbenannte Verzweigung)',
        'fr': '(branche sans nom)',
        'es': '(rama sin nombre)',
    },
}


# 導覽面板原本底部有「已走過」麵包屑，改版拿掉了。這個 key 曾隨本 migration 的
# 前一版寫進 DB，在這裡一併清掉，早期套用過的環境才不會留下孤兒字串。
SUPERSEDED_KEYS = ['game.flowchart.tour.path']


def add_strings(apps, schema_editor):
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    Translation.objects.filter(key__in=SUPERSEDED_KEYS).delete()

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
    Translation.objects.filter(key__in=list(STRINGS.keys()) + SUPERSEDED_KEYS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0024_flowchart_legend_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
