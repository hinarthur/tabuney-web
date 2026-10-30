"""
把 tier_new 是 NULL 的 Member 依 tier_legacy 補上 tier_new。

這是拆除 tier_legacy/legacy_code 相容層的第一步：Member.tier_code 目前在
tier_new 為 None 時會 fallback 讀 tier_legacy 顯示等級，拿掉 fallback 前
必須確保現存資料都已經有 tier_new，否則這些帳號的等級顯示會全部變回預設值。

映射對齊 Member.tier_code 屬性目前的 legacy 對照表（member/models.py），
不使用舊版 migration 0013 的 A→free/B→basic 映射：'basic' tier 即將在
後續 migration 退場，直接把舊版 'B'（basic）使用者併到 'member'，
避免這批帳號的 tier_new 才剛補上就要在下一個 migration 再搬一次。
"""

from django.db import migrations

LEGACY_TO_NEW = {
    'A': 'free',
    'B': 'member',
    'C': 'subscriber',
}


def backfill(apps, schema_editor):
    Member = apps.get_model('member', 'Member')
    Tier = apps.get_model('member', 'Tier')

    for member in Member.objects.filter(tier_new__isnull=True):
        new_code = LEGACY_TO_NEW.get(member.tier_legacy or 'A', 'free')
        try:
            member.tier_new = Tier.objects.get(code=new_code)
        except Tier.DoesNotExist:
            continue
        member.save(update_fields=['tier_new'])


class Migration(migrations.Migration):

    dependencies = [
        ('member', '0015_add_source_field'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
