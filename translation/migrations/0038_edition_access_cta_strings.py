"""Edition 各分頁標題列右上角 CTA 的按鈕字樣。

按鈕很窄（右上角、要能跟 h1 並排、窄螢幕還要掉到下一行），所以文字必須極短
——info 分頁那塊完整區塊才負責解釋內容與條件。數量／價格由模板另外接在
<small> 裡，不寫進譯文（見 0036 的說明：譯文寫死金額日後調價一定會漏）。
"""

from django.db import migrations

STRINGS = {
    # 未登入，以及免費名額用完要加購時共用：都是「去取得」的動作
    'game.unlock.cta.get': {
        'en': 'Get Edition Access',
        'zh': '取得版本專享',
        'ja': 'エディションアクセス',
        'de': 'Edition Access holen',
        'fr': 'Obtenir Edition Access',
        'es': 'Obtener Edition Access',
    },
    # 還有免費名額時
    'game.unlock.cta.free': {
        'en': 'Unlock free',
        'zh': '免費取得',
        'ja': '無料で取得',
        'de': 'Gratis freischalten',
        'fr': 'Obtenir gratuitement',
        'es': 'Obtener gratis',
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
        ('translation', '0037_collection_access_filter_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
