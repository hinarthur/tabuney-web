"""結帳確認信的文案（commerce/checkout_consent.py 的 EMAIL_COPY）進 translation admin。

信件之前是寫死的英文，只有買家同意的聲明原文是買家語言。現在主旨、標籤與法律說明段
也依 CheckoutConsent.language 取用，涵蓋 settings.LANGUAGES 六種語言。
內容含法律說明，目前是未經法務審閱的草稿。is_synced 設為 False，VPS 才會收到。
"""

from django.db import migrations

PREFIX = 'checkout.consent.'
LANGS = ('en', 'zh', 'ja', 'de', 'fr', 'es')


def add_strings(apps, schema_editor):
    from commerce.checkout_consent import EMAIL_COPY

    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    for lang in LANGS:
        tribe = Tribe.objects.filter(language=lang).first()
        if tribe is None:
            continue
        for name, value in EMAIL_COPY[lang].items():
            Translation.objects.update_or_create(
                tribe=tribe, key=PREFIX + name,
                defaults={'value': value, 'is_synced': False},
            )


def remove_strings(apps, schema_editor):
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(key__startswith=PREFIX + 'email_').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0052_checkout_consent_more_languages'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
