"""聯絡信箱統一為 info@tabuney.com。

舊地址 info@ttoper.com 已經寫進 Translation 資料表（見 0015_faq_page_strings），
改程式碼與模板不會更新資料庫裡的值，所以這裡直接取代。is_synced 要設回 False，
否則 VPS 不會收到更新。
"""

from django.db import migrations

OLD = 'info@ttoper.com'
NEW = 'info@tabuney.com'


def swap(old, new):
    def run(apps, schema_editor):
        Translation = apps.get_model('translation', 'Translation')
        for row in Translation.objects.filter(value__contains=old):
            Translation.objects.filter(pk=row.pk).update(
                value=row.value.replace(old, new), is_synced=False, synced_at=None,
            )
    return run


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0049_checkout_consent_strings'),
    ]

    operations = [
        migrations.RunPython(swap(OLD, NEW), swap(NEW, OLD)),
    ]
