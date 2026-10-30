"""
Flowchart 分頁新增「提出改善建議」按鈕（會員限定）：按下後在 modal 內對目前選中的
ruleset 寫文字建議，存成待審核的 FlowchartSuggestion。這裡是該功能用到的 UI 字串。
"""

from django.db import migrations

STRINGS = {
    'game.flowchart.suggest.title': {
        'en': 'Suggest an improvement',
        'zh': '提出改善建議',
        'ja': '改善を提案する',
        'de': 'Verbesserung vorschlagen',
        'fr': 'Proposer une amélioration',
        'es': 'Sugerir una mejora',
    },
    'game.flowchart.suggest.modal.title': {
        'en': 'Suggest an improvement to this flowchart',
        'zh': '為這張流程圖提出改善建議',
        'ja': 'このフローチャートへの改善提案',
        'de': 'Verbesserung für dieses Flussdiagramm vorschlagen',
        'fr': 'Proposer une amélioration de cet organigramme',
        'es': 'Sugerir una mejora para este diagrama',
    },
    'game.flowchart.suggest.modal.desc': {
        'en': 'Spotted a step that is wrong, missing, or hard to follow? Tell us '
              'what you would change — we read every suggestion and adjust the '
              'chart by hand.',
        'zh': '發現哪一步寫錯了、漏掉了，或看不懂？告訴我們你會怎麼改 —— '
              '每則建議我們都會看過，再人工調整流程圖。',
        'ja': '間違っている・抜けている・分かりにくいステップはありますか？'
              'どう直したいかをお知らせください。いただいた提案はすべて読み、'
              '手作業でフローチャートを修正します。',
        'de': 'Ein Schritt ist falsch, fehlt oder ist schwer nachvollziehbar? '
              'Schreiben Sie uns, was Sie ändern würden — wir lesen jeden '
              'Vorschlag und passen das Diagramm von Hand an.',
        'fr': "Une étape est fausse, manquante ou difficile à suivre ? "
              "Dites-nous ce que vous changeriez — nous lisons chaque "
              "suggestion et ajustons le schéma à la main.",
        'es': '¿Hay un paso equivocado, que falta o difícil de seguir? '
              'Cuéntanos qué cambiarías: leemos todas las sugerencias y '
              'ajustamos el diagrama a mano.',
    },
    'game.flowchart.suggest.modal.placeholder': {
        'en': 'For example: after "Draw a card" the chart should also allow '
              'passing your turn.',
        'zh': '例如：「抽一張牌」之後應該還可以選擇跳過這回合。',
        'ja': '例：「カードを1枚引く」の後に、手番をパスする選択肢も必要です。',
        'de': 'Zum Beispiel: Nach „Karte ziehen“ sollte auch das Aussetzen '
              'möglich sein.',
        'fr': "Par exemple : après « Piocher une carte », on devrait aussi "
              "pouvoir passer son tour.",
        'es': 'Por ejemplo: después de «Roba una carta» también debería '
              'poder pasarse el turno.',
    },
    'game.flowchart.suggest.modal.login-required': {
        'en': 'Sign in to send us a suggestion for this flowchart.',
        'zh': '登入後即可對這張流程圖提出建議。',
        'ja': 'ログインすると、このフローチャートに提案を送れます。',
        'de': 'Melden Sie sich an, um einen Vorschlag zu diesem Flussdiagramm '
              'zu senden.',
        'fr': "Connectez-vous pour nous envoyer une suggestion sur cet "
              "organigramme.",
        'es': 'Inicia sesión para enviarnos una sugerencia sobre este diagrama.',
    },
    'game.flowchart.suggest.success': {
        'en': "Thanks! We'll take your suggestion into account.",
        'zh': '謝謝你的建議，我們會參考修改。',
        'ja': 'ご提案ありがとうございます。参考にさせていただきます。',
        'de': 'Danke! Wir berücksichtigen Ihren Vorschlag.',
        'fr': 'Merci ! Nous tiendrons compte de votre suggestion.',
        'es': '¡Gracias! Tendremos en cuenta tu sugerencia.',
    },
    'game.flowchart.suggest.error.empty': {
        'en': 'Please write your suggestion first.',
        'zh': '請先寫下你的建議。',
        'ja': '提案の内容を入力してください。',
        'de': 'Bitte schreiben Sie zuerst Ihren Vorschlag.',
        'fr': "Veuillez d'abord écrire votre suggestion.",
        'es': 'Escribe primero tu sugerencia.',
    },
    'game.flowchart.suggest.error.too-long': {
        'en': 'Your suggestion is too long (2000 characters max).',
        'zh': '建議內容太長了（最多 2000 字）。',
        'ja': '提案が長すぎます（最大2000文字）。',
        'de': 'Ihr Vorschlag ist zu lang (max. 2000 Zeichen).',
        'fr': 'Votre suggestion est trop longue (2000 caractères maximum).',
        'es': 'Tu sugerencia es demasiado larga (máximo 2000 caracteres).',
    },
    'game.flowchart.suggest.error.generic': {
        'en': 'Something went wrong. Please try again.',
        'zh': '出了點問題，請再試一次。',
        'ja': '問題が発生しました。もう一度お試しください。',
        'de': 'Etwas ist schiefgelaufen. Bitte versuchen Sie es erneut.',
        'fr': "Une erreur s'est produite. Veuillez réessayer.",
        'es': 'Algo salió mal. Inténtalo de nuevo.',
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
        ('translation', '0027_flowchart_footnote'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
