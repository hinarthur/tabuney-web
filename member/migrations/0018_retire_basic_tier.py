"""
'basic' tier 退場。

確認本地開發庫目前 0 筆 Member 指向它（member 概念已被 'member' tier 取代）。
正式站數字可能不同，所以這裡「先搬再刪」而不是直接刪：任何殘留指向 'basic'
的 Member 先改指到 'member'，再刪除 Tier 列本身，避免正式站因為還有人在用
而讓刪除留下垂懸資料或違反 PROTECT 外鍵約束。
"""

from django.db import migrations


def retire_basic(apps, schema_editor):
    Member = apps.get_model('member', 'Member')
    Tier = apps.get_model('member', 'Tier')

    try:
        basic = Tier.objects.get(code='basic')
    except Tier.DoesNotExist:
        return

    member_tier = Tier.objects.filter(code='member').first()
    if member_tier is not None:
        Member.objects.filter(tier_new=basic).update(tier_new=member_tier)

    # PROTECT 外鍵：搬完後如果還有殘留（例如 'member' tier 也不存在），
    # delete() 會直接拋 ProtectedError 讓 migration 失敗，而不是靜默留垂懸資料。
    basic.delete()


def restore_basic(apps, schema_editor):
    Tier = apps.get_model('member', 'Tier')
    Tier.objects.get_or_create(
        code='basic', defaults={'name': 'Basic Member', 'limits': {}},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('member', '0017_remove_legacy_tier_fields'),
    ]

    operations = [
        migrations.RunPython(retire_basic, restore_basic),
    ]
