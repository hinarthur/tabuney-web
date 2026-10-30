"""
seo.default.title 已經改成直接寫死在 templates/base.html（<title> 與 og:title
都固定顯示 "Tabuney"），不再透過翻譯系統管理，這裡把 DB 裡的字串清掉。

seo.default.description 不受影響——多個頁面（about/terms/privacy 等）仍在用它。
"""

from django.db import migrations

KEY = 'seo.default.title'

# 對應 0011_simplify_seo_default_title.py 的值，供 reverse 還原
OLD_VALUE = 'Tabuney'


def remove_title(apps, schema_editor):
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(key=KEY).delete()


def restore_title(apps, schema_editor):
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')
    for tribe in Tribe.objects.filter(language__in=['en', 'zh', 'ja', 'de', 'fr', 'es']):
        Translation.objects.update_or_create(
            tribe=tribe, key=KEY, defaults={'value': OLD_VALUE, 'is_synced': False},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0011_simplify_seo_default_title'),
    ]

    operations = [
        migrations.RunPython(remove_title, restore_title),
    ]
