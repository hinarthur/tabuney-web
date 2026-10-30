"""
edition_detail 流程圖工具列新增 ℹ️ 按鈕，解說流程圖裡各種形狀（橢圓/菱形/雙框矩形/
缺角矩形/色塊分區/虛線框）分別代表的意思，方便玩家看懂 AI 產生的流程圖。
"""

from django.db import migrations

STRINGS = {
    'game.flowchart.legend': {
        'en': 'Icon Legend',
        'zh': '圖示說明',
        'ja': 'アイコンの説明',
        'de': 'Symbolerklärung',
        'fr': 'Légende des icônes',
        'es': 'Leyenda de iconos',
    },
    'game.flowchart.legend.title': {
        'en': 'Flowchart Icon Legend',
        'zh': '流程圖圖示說明',
        'ja': 'フローチャートのアイコン説明',
        'de': 'Symbolerklärung des Flussdiagramms',
        'fr': 'Légende des icônes de l’organigramme',
        'es': 'Leyenda de iconos del diagrama de flujo',
    },
    'game.flowchart.legend.start.label': {
        'en': 'Start',
        'zh': '開始',
        'ja': '開始',
        'de': 'Start',
        'fr': 'Début',
        'es': 'Inicio',
    },
    'game.flowchart.legend.start.def': {
        'en': 'Where this part of the flow begins.',
        'zh': '這段流程的起點。',
        'ja': 'このフローの開始地点です。',
        'de': 'Hier beginnt dieser Teil des Ablaufs.',
        'fr': 'Le point de départ de cette partie du déroulement.',
        'es': 'Donde comienza esta parte del flujo.',
    },
    'game.flowchart.legend.end.label': {
        'en': 'End',
        'zh': '結束',
        'ja': '終了',
        'de': 'Ende',
        'fr': 'Fin',
        'es': 'Fin',
    },
    'game.flowchart.legend.end.def': {
        'en': 'Where this part of the flow finishes.',
        'zh': '這段流程的終點。',
        'ja': 'このフローの終了地点です。',
        'de': 'Hier endet dieser Teil des Ablaufs.',
        'fr': 'Le point d’arrivée de cette partie du déroulement.',
        'es': 'Donde termina esta parte del flujo.',
    },
    'game.flowchart.legend.decision.label': {
        'en': 'Decision',
        'zh': '決策 / 分支',
        'ja': '分岐',
        'de': 'Entscheidung',
        'fr': 'Décision',
        'es': 'Decisión',
    },
    'game.flowchart.legend.decision.def': {
        'en': 'A choice or check that branches the flow into different paths.',
        'zh': '需要判斷的地方，會依結果走向不同分支。',
        'ja': '判断が必要な箇所で、結果によって流れが分岐します。',
        'de': 'Eine Entscheidung oder Prüfung, die den Ablauf in verschiedene Pfade verzweigt.',
        'fr': 'Un choix ou une vérification qui oriente le déroulement vers différents chemins.',
        'es': 'Una elección o comprobación que ramifica el flujo en distintos caminos.',
    },
    'game.flowchart.legend.parallel.label': {
        'en': 'Parallel step',
        'zh': '同時進行',
        'ja': '同時進行',
        'de': 'Paralleler Schritt',
        'fr': 'Étape simultanée',
        'es': 'Paso simultáneo',
    },
    'game.flowchart.legend.parallel.def': {
        'en': 'Steps that happen at the same time as other steps.',
        'zh': '與其他步驟同時發生的動作。',
        'ja': '他のステップと同時に行われる動作です。',
        'de': 'Schritte, die gleichzeitig mit anderen Schritten stattfinden.',
        'fr': 'Des étapes qui se déroulent en même temps que d’autres.',
        'es': 'Pasos que ocurren al mismo tiempo que otros pasos.',
    },
    'game.flowchart.legend.phase.label': {
        'en': 'Phase marker',
        'zh': '階段標記',
        'ja': 'フェーズ標識',
        'de': 'Phasenmarkierung',
        'fr': 'Repère de phase',
        'es': 'Marcador de fase',
    },
    'game.flowchart.legend.phase.def': {
        'en': 'Marks a named phase or sub-step within the flow.',
        'zh': '標示流程中某個具名的階段或子步驟。',
        'ja': 'フロー内の名前付きフェーズや小ステップを示します。',
        'de': 'Markiert eine benannte Phase oder einen Teilschritt im Ablauf.',
        'fr': 'Repère une phase ou sous-étape nommée dans le déroulement.',
        'es': 'Marca una fase o subpaso con nombre dentro del flujo.',
    },
    'game.flowchart.legend.action.label': {
        'en': 'Action / step',
        'zh': '動作／步驟',
        'ja': 'アクション／手順',
        'de': 'Aktion / Schritt',
        'fr': 'Action / étape',
        'es': 'Acción / paso',
    },
    'game.flowchart.legend.action.def': {
        'en': 'A regular action or instruction to follow.',
        'zh': '一般的動作或指示。',
        'ja': '通常のアクションや手順です。',
        'de': 'Eine normale Aktion oder Anweisung.',
        'fr': 'Une action ou instruction ordinaire à suivre.',
        'es': 'Una acción o instrucción habitual a seguir.',
    },
    'game.flowchart.legend.group.label': {
        'en': 'Phase region',
        'zh': '階段分區',
        'ja': 'フェーズ領域',
        'de': 'Phasenbereich',
        'fr': 'Zone de phase',
        'es': 'Región de fase',
    },
    'game.flowchart.legend.group.def': {
        'en': 'The colored dashed box groups all steps belonging to one phase (e.g. Preparation, Gameflow, Endgame).',
        'zh': '虛線色塊框住屬於同一階段的所有步驟（例如準備、遊戲流程、結算）。',
        'ja': '色付きの点線枠は、同じフェーズ（準備・進行・終了など）に属するすべてのステップをまとめています。',
        'de': 'Der farbige gestrichelte Kasten fasst alle Schritte einer Phase zusammen (z. B. Vorbereitung, Spielverlauf, Spielende).',
        'fr': 'La zone en pointillés colorée regroupe toutes les étapes d’une même phase (ex. préparation, déroulement, fin de partie).',
        'es': 'El recuadro punteado de color agrupa todos los pasos de una misma fase (p. ej., preparación, desarrollo, final).',
    },
    'game.flowchart.legend.note.label': {
        'en': 'Note',
        'zh': '補充說明',
        'ja': '補足説明',
        'de': 'Hinweis',
        'fr': 'Remarque',
        'es': 'Nota',
    },
    'game.flowchart.legend.note.def': {
        'en': 'Extra notes or reminders that are not part of the main flow.',
        'zh': '非主流程的額外提醒或補充資訊。',
        'ja': 'メインフローには含まれない補足情報や注意事項です。',
        'de': 'Zusätzliche Hinweise, die nicht Teil des Hauptablaufs sind.',
        'fr': 'Des remarques supplémentaires qui ne font pas partie du déroulement principal.',
        'es': 'Notas adicionales que no forman parte del flujo principal.',
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
        ('translation', '0023_translation_is_used_translation_used_checked_at'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
