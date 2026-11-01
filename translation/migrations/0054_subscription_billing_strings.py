"""會員頁訂閱操作結果訊息、續費失敗提示與更新付款方式按鈕。

key 與 commerce.views（_text 後備英文）及 membership.html 對應。
"""

from django.db import migrations

STRINGS = {
    'membership.subscription.msg.cancelled': {
        'en': 'Auto-renewal is turned off. Your access continues until the end of the current period.',
        'zh': '已關閉自動續訂。你的權限會持續到本期結束。',
        'ja': '自動更新をオフにしました。現在の期間の終了までご利用いただけます。',
        'de': 'Die automatische Verlängerung ist deaktiviert. Dein Zugang bleibt bis zum Ende des aktuellen Zeitraums bestehen.',
        'fr': "Le renouvellement automatique est désactivé. Votre accès reste actif jusqu'à la fin de la période en cours.",
        'es': 'La renovación automática está desactivada. Tu acceso continúa hasta el final del periodo actual.',
    },
    'membership.subscription.msg.resumed': {
        'en': 'Auto-renewal is turned back on.',
        'zh': '已重新開啟自動續訂。',
        'ja': '自動更新を再開しました。',
        'de': 'Die automatische Verlängerung ist wieder aktiviert.',
        'fr': 'Le renouvellement automatique est de nouveau activé.',
        'es': 'La renovación automática se ha vuelto a activar.',
    },
    'membership.subscription.msg.error': {
        'en': 'Something went wrong and your subscription was not changed. Please try again later or contact info@tabuney.com.',
        'zh': '發生錯誤，你的訂閱沒有任何變更。請稍後再試，或聯絡 info@tabuney.com。',
        'ja': 'エラーが発生したため、サブスクリプションは変更されていません。しばらくしてからもう一度お試しいただくか、info@tabuney.com までご連絡ください。',
        'de': 'Es ist ein Fehler aufgetreten, dein Abonnement wurde nicht geändert. Bitte versuche es später erneut oder schreibe an info@tabuney.com.',
        'fr': "Une erreur s'est produite et votre abonnement n'a pas été modifié. Réessayez plus tard ou écrivez à info@tabuney.com.",
        'es': 'Se produjo un error y tu suscripción no se modificó. Inténtalo de nuevo más tarde o escribe a info@tabuney.com.',
    },
    'membership.subscription.msg.already': {
        'en': 'You already have an active subscription.',
        'zh': '你已經有一份有效的訂閱。',
        'ja': 'すでに有効なサブスクリプションがあります。',
        'de': 'Du hast bereits ein aktives Abonnement.',
        'fr': 'Vous avez déjà un abonnement actif.',
        'es': 'Ya tienes una suscripción activa.',
    },
    'membership.subscription.past_due': {
        'en': 'Payment failed. Please update your payment method to keep access.',
        'zh': '扣款失敗。請更新付款方式以保留權限。',
        'ja': 'お支払いに失敗しました。アクセスを維持するには、お支払い方法を更新してください。',
        'de': 'Die Zahlung ist fehlgeschlagen. Bitte aktualisiere deine Zahlungsmethode, um den Zugang zu behalten.',
        'fr': "Le paiement a échoué. Mettez à jour votre moyen de paiement pour conserver l'accès.",
        'es': 'El pago falló. Actualiza tu método de pago para mantener el acceso.',
    },
    'membership.subscription.btn.update_payment': {
        'en': 'Update payment method',
        'zh': '更新付款方式',
        'ja': 'お支払い方法を更新',
        'de': 'Zahlungsmethode aktualisieren',
        'fr': 'Mettre à jour le moyen de paiement',
        'es': 'Actualizar método de pago',
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
        ('translation', '0053_checkout_consent_email_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
