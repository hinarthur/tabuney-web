"""結帳前同意頁（commerce/checkout_consent.py）的文案，讓它們出現在 translation admin。

文案是具法律效力的放棄聲明，所以只種 en 與 zh 兩種，其餘語言不機器翻譯：
load_copy() 在某語言沒有 digital / service / terms 三條時會整頁退回英文，
不會出現半翻譯的聲明。要新增語言，三條法律文案一次補齊即可。

key 前綴 checkout.consent. 由 load_copy() 拼接，掃描 key 使用狀況時抓不到字面字串，
已登記在 translation/services.py 的 KNOWN_DYNAMIC_PREFIXES，否則會被誤判成未使用而刪除。
"""

from django.db import migrations

PREFIX = 'checkout.consent.'


def add_strings(apps, schema_editor):
    from commerce.checkout_consent import COPY

    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    for lang in ('en', 'zh'):
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
    Translation.objects.filter(key__startswith=PREFIX).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0048_home_overview_art_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
