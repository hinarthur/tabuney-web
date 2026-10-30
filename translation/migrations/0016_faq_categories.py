"""
FAQ 頁面問答分成三類，補上分類小標題翻譯字串。
"""

from django.db import migrations

STRINGS = {
    'faq.category.features': {
        'en': 'Features',
        'zh': '功能',
        'ja': '機能',
        'de': 'Funktionen',
        'fr': 'Fonctionnalités',
        'es': 'Funciones',
    },
    'faq.category.plans': {
        'en': 'Plans & Account',
        'zh': '方案與帳號',
        'ja': 'プラン・アカウント',
        'de': 'Pläne & Konto',
        'fr': 'Formules et compte',
        'es': 'Planes y cuenta',
    },
    'faq.category.privacy': {
        'en': 'Privacy & Data',
        'zh': '隱私與資料',
        'ja': 'プライバシーとデータ',
        'de': 'Datenschutz & Daten',
        'fr': 'Confidentialité et données',
        'es': 'Privacidad y datos',
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
        ('translation', '0015_faq_page_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
