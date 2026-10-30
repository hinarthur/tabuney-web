"""收藏頁 Edition Access 篩選的第二個選項。

篩選改成與 status / rating 同一套「全選＝不篩選」的多選，所以除了原本的
「有版本專享」，還需要對應的「沒有版本專享」，兩個預設都勾選。

（原本是單一開關且預設未勾選，點一下就變成 AND 縮窄——會員手上通常只有幾款
有版本專享，於是「點一下全部不見了」。）
"""

from django.db import migrations

STRINGS = {
    'game.mycollection.access_none': {
        'en': 'Without Edition Access',
        'zh': '沒有版本專享',
        'ja': 'エディションアクセスなし',
        'de': 'Ohne Edition Access',
        'fr': 'Sans Edition Access',
        'es': 'Sin Edition Access',
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
        ('translation', '0036_edition_access_pricing_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
