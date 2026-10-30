"""
membership.html 的優惠價格列（早鳥徽章／優惠說明）原本是寫死英文，
改用 {% t %} 翻譯 key，六語言都補上。
"""

from django.db import migrations

STRINGS = {
    'membership.price.discount_badge': {
        'en': 'Save 30%',
        'zh': '省30%',
        'ja': '30%オフ',
        'de': '30% sparen',
        'fr': '-30%',
        'es': 'Ahorra 30%',
    },
    'membership.price.early_supporter': {
        'en': 'Early Supporter Price',
        'zh': '早鳥優惠價',
        'ja': 'アーリーサポーター価格',
        'de': 'Preis für frühe Unterstützer',
        'fr': 'Tarif premier soutien',
        'es': 'Precio de apoyo anticipado',
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
        ('translation', '0018_legend_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
