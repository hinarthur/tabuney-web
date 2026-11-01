"""Beta 模式（settings.BETA_MODE）用到的字串：logo 旁的 Beta 標籤，以及未登入者
Rulesbot 當日題數用完時的登入提示。

key 與 base.html、edition_detail_rulesbot.html 對應。
"""

from django.db import migrations

STRINGS = {
    'site.beta': {
        'en': 'Beta',
        'zh': 'Beta',
        'ja': 'Beta',
        'de': 'Beta',
        'fr': 'Bêta',
        'es': 'Beta',
    },
    'game.chat.anon.limit_login': {
        'en': "You've used today's free questions. Log in to keep asking with no limit.",
        'zh': '今天的免費提問已用完。登入後即可不限次數繼續提問。',
        'ja': '本日の無料質問回数を使い切りました。ログインすると回数無制限で質問できます。',
        'de': 'Du hast deine kostenlosen Fragen für heute aufgebraucht. Melde dich an, um unbegrenzt weiterzufragen.',
        'fr': "Vous avez utilisé vos questions gratuites du jour. Connectez-vous pour continuer sans limite.",
        'es': 'Has usado tus preguntas gratuitas de hoy. Inicia sesión para seguir preguntando sin límite.',
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
        ('translation', '0054_subscription_billing_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
