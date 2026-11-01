"""使用條款與隱私政策的連結文字統一，結帳同意頁改用現成的 key。

頁尾連結原本叫 Terms of Use，但頁面標題是 Terms of Service，兩者指向同一頁，
所以把 terms_of_use 的英文改成 Terms of Service（其他語言本來就只是「使用條款」，不動）。
結帳同意頁的 checkout.consent.back / terms_label / privacy_label 與既有的
btn.back / terms_of_use / privacy_policy 重複，這裡刪掉，load_copy() 改讀現成 key。
is_synced 要設回 False，否則 VPS 不會收到更新。
"""

from django.db import migrations

PREFIX = 'checkout.consent.'
DROPPED = {
    'en': {'back': 'Back', 'terms_label': 'Terms of Service', 'privacy_label': 'Privacy Policy'},
    'zh': {'back': '返回', 'terms_label': '使用條款', 'privacy_label': '私隱政策'},
}


def set_terms_label(value):
    def run(apps, schema_editor):
        Translation = apps.get_model('translation', 'Translation')
        Translation.objects.filter(key='terms_of_use', tribe__language='en').update(
            value=value, is_synced=False, synced_at=None,
        )
    return run


def forwards(apps, schema_editor):
    set_terms_label('Terms of Service')(apps, schema_editor)
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(
        key__in=[PREFIX + name for name in DROPPED['en']],
    ).delete()


def backwards(apps, schema_editor):
    set_terms_label('Terms of Use')(apps, schema_editor)
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')
    for lang, strings in DROPPED.items():
        tribe = Tribe.objects.filter(language=lang).first()
        if tribe is None:
            continue
        for name, value in strings.items():
            Translation.objects.update_or_create(
                tribe=tribe, key=PREFIX + name,
                defaults={'value': value, 'is_synced': False},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0050_contact_email_tabuney'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
