"""付款完成回跳頁：「處理中」提示。

使用者付完款被導回 edition 頁，但解鎖還沒建立（webhook 沒到、Stripe 那邊
還沒標記為已付款，或向 Stripe 確認時暫時失敗）。這時不能假裝成功，也不能
什麼都不說——使用者會以為付了錢沒東西。誠實地說「處理中」，並告訴他怎麼做。

成功的情況沿用既有的 game.unlock.success。
"""

from django.db import migrations

STRINGS = {
    'game.unlock.return.pending': {
        'en': (
            "Your payment went through, but Edition Access is not showing on your "
            "account yet. This usually takes a few seconds — please refresh this page "
            "in a moment. If it is still missing after a few minutes, contact us and "
            "we will sort it out."
        ),
        'zh': (
            '你的付款已完成，但版本專享還沒顯示在你的帳號上。通常只需要幾秒鐘，'
            '請稍後重新整理本頁。如果幾分鐘後仍沒出現，請聯絡我們，我們會處理。'
        ),
        'ja': (
            'お支払いは完了しましたが、エディションアクセスがまだアカウントに反映'
            'されていません。通常は数秒ほどで反映されますので、少し待ってからこの'
            'ページを再読み込みしてください。数分たっても反映されない場合はご連絡'
            'ください。対応いたします。'
        ),
        'de': (
            'Deine Zahlung ist durchgegangen, aber Edition Access erscheint noch nicht '
            'auf deinem Konto. Das dauert meist nur wenige Sekunden — bitte lade die '
            'Seite gleich neu. Fehlt es nach einigen Minuten noch, melde dich bei uns, '
            'dann klären wir das.'
        ),
        'fr': (
            "Votre paiement a bien été effectué, mais Edition Access n'apparaît pas encore "
            "sur votre compte. Cela ne prend généralement que quelques secondes : "
            "actualisez la page dans un instant. S'il manque encore après quelques "
            "minutes, contactez-nous et nous réglerons cela."
        ),
        'es': (
            'Tu pago se completó, pero Edition Access aún no aparece en tu cuenta. '
            'Normalmente tarda unos segundos: actualiza esta página en un momento. Si '
            'tras unos minutos sigue sin aparecer, contáctanos y lo resolveremos.'
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
    Translation.objects.filter(key__in=STRINGS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0038_edition_access_cta_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
