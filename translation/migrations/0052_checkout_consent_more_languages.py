"""結帳同意頁文案補上 ja / de / fr / es，涵蓋 settings.LANGUAGES 全部六種語言。

文案取自 commerce/checkout_consent.py 的 COPY。它們是具法律效力的放棄聲明，
目前是未經法務審閱的草稿；之後要修改請直接在 translation admin 改。
back / terms_label / privacy_label 不在這裡：那三項共用 btn.back、terms_of_use、
privacy_policy（見 0051）。
"""

from django.db import migrations

PREFIX = 'checkout.consent.'
LANGS = ('ja', 'de', 'fr', 'es')


def add_strings(apps, schema_editor):
    from commerce.checkout_consent import COPY

    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    for lang in LANGS:
        tribe = Tribe.objects.filter(language=lang).first()
        if tribe is None:
            continue
        for name, value in COPY[lang].items():
            Translation.objects.update_or_create(
                tribe=tribe, key=PREFIX + name,
                defaults={'value': value, 'is_synced': False},
            )


def remove_strings(apps, schema_editor):
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(key__startswith=PREFIX, tribe__language__in=LANGS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0051_unify_terms_privacy_labels'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
