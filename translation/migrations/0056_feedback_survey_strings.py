"""
用戶回饋擴充用到的 UI 字串：
  * 流程圖導覽（FlowchartTour）中對單一節點的回饋 —— game.flowchart.tour.feedback.*
  * edition / 全站問卷的浮動按鈕與 modal 外框 —— feedback.survey.*

問卷的題目與選項不在這裡，那些是在 admin 編輯的多語 JSON（feedback.Survey 等）。
德文沿用站上其他字串的 du 稱呼。
"""

from django.db import migrations

STRINGS = {
    # ── 導覽中的節點回饋 ──
    'game.flowchart.tour.feedback.button': {
        'en': 'Feedback on this step',
        'zh': '回饋這一步',
        'ja': 'このステップへのフィードバック',
        'de': 'Feedback zu diesem Schritt',
        'fr': 'Un avis sur cette étape',
        'es': 'Comentar este paso',
    },
    'game.flowchart.tour.feedback.placeholder': {
        'en': 'What is wrong, missing or unclear about this step?',
        'zh': '這一步哪裡寫錯、漏掉了，或看不懂？',
        'ja': 'このステップの間違い・抜け・分かりにくい点を教えてください',
        'de': 'Was ist an diesem Schritt falsch, fehlt oder ist unklar?',
        'fr': "Qu'est-ce qui est faux, manquant ou peu clair dans cette étape ?",
        'es': '¿Qué está mal, falta o no se entiende en este paso?',
    },
    'game.flowchart.tour.feedback.success': {
        'en': "Thanks! We'll take a look at this step.",
        'zh': '謝謝！我們會檢查這一步。',
        'ja': 'ありがとうございます！このステップを確認します。',
        'de': 'Danke! Wir sehen uns diesen Schritt an.',
        'fr': 'Merci ! Nous allons examiner cette étape.',
        'es': '¡Gracias! Revisaremos este paso.',
    },

    # ── 問卷浮動按鈕 ──
    'feedback.survey.fab.edition': {
        'en': 'Quick survey (1 min)',
        'zh': '1 分鐘小問卷',
        'ja': '1分アンケート',
        'de': 'Kurze Umfrage (1 Min.)',
        'fr': 'Mini-sondage (1 min)',
        'es': 'Encuesta rápida (1 min)',
    },
    'feedback.survey.fab.site': {
        'en': 'Help us improve Tabuney',
        'zh': '幫我們改善 Tabuney',
        'ja': 'Tabuney の改善にご協力ください',
        'de': 'Hilf uns, Tabuney zu verbessern',
        'fr': 'Aidez-nous à améliorer Tabuney',
        'es': 'Ayúdanos a mejorar Tabuney',
    },
    'feedback.survey.dismiss': {
        'en': 'Not now',
        'zh': '先不要',
        'ja': '今はしない',
        'de': 'Jetzt nicht',
        'fr': 'Pas maintenant',
        'es': 'Ahora no',
    },

    # ── 問卷 modal ──
    'feedback.survey.submit': {
        'en': 'Send',
        'zh': '送出',
        'ja': '送信',
        'de': 'Senden',
        'fr': 'Envoyer',
        'es': 'Enviar',
    },
    'feedback.survey.close': {
        'en': 'Close',
        'zh': '關閉',
        'ja': '閉じる',
        'de': 'Schließen',
        'fr': 'Fermer',
        'es': 'Cerrar',
    },
    'feedback.survey.thanks': {
        'en': 'Thank you! Your answers help us make better guides.',
        'zh': '謝謝你！你的回答能幫我們把內容做得更好。',
        'ja': 'ありがとうございました！いただいた回答はより良いガイド作りに役立てます。',
        'de': 'Danke! Deine Antworten helfen uns, bessere Anleitungen zu machen.',
        'fr': 'Merci ! Vos réponses nous aident à améliorer nos guides.',
        'es': '¡Gracias! Tus respuestas nos ayudan a hacer mejores guías.',
    },
    'feedback.survey.multi_hint': {
        'en': 'Select all that apply',
        'zh': '可複選',
        'ja': '当てはまるものをすべて選択',
        'de': 'Mehrfachauswahl möglich',
        'fr': 'Plusieurs choix possibles',
        'es': 'Puedes elegir varias',
    },
    'feedback.survey.required_note': {
        'en': 'Required',
        'zh': '必填',
        'ja': '必須',
        'de': 'Pflichtfeld',
        'fr': 'Obligatoire',
        'es': 'Obligatorio',
    },
    'feedback.survey.error.required': {
        'en': 'Please answer this question.',
        'zh': '請回答這一題。',
        'ja': 'この質問にお答えください。',
        'de': 'Bitte beantworte diese Frage.',
        'fr': 'Veuillez répondre à cette question.',
        'es': 'Responde a esta pregunta.',
    },
    'feedback.survey.error.too_long': {
        'en': 'Your answer is too long.',
        'zh': '回答太長了。',
        'ja': '回答が長すぎます。',
        'de': 'Deine Antwort ist zu lang.',
        'fr': 'Votre réponse est trop longue.',
        'es': 'Tu respuesta es demasiado larga.',
    },
    'feedback.survey.error.generic': {
        'en': 'Something went wrong. Please try again.',
        'zh': '發生錯誤，請再試一次。',
        'ja': 'エラーが発生しました。もう一度お試しください。',
        'de': 'Etwas ist schiefgelaufen. Bitte versuche es erneut.',
        'fr': 'Une erreur s’est produite. Veuillez réessayer.',
        'es': 'Algo ha salido mal. Inténtalo de nuevo.',
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
    Translation.objects.filter(key__in=STRINGS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0055_beta_mode_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
