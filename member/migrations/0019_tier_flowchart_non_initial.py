"""
新 tier feature 'flowchart_non_initial'（瀏覽非入門流程圖）寫進既有 Tier.limits。

registry default 是 0（fail closed），所以不回填的話 subscriber / admin 會在
上線瞬間失去原本看得到的非入門流程圖。這裡只補「還沒有這個 key」的 tier，
不覆蓋 admin 後台已經手動調過的值。

放行對象比照這個旗標存在前的行為（原本寫死 is_subscriber_or_higher）：
subscriber / admin 開，其餘關。
"""

from django.db import migrations

KEY = "flowchart_non_initial"
ALLOWED = ("subscriber", "admin")


def add_key(apps, schema_editor):
    Tier = apps.get_model("member", "Tier")
    for tier in Tier.objects.all():
        limits = tier.limits if isinstance(tier.limits, dict) else {}
        if KEY in limits:
            continue
        limits[KEY] = 1 if tier.code in ALLOWED else 0
        tier.limits = limits
        tier.save(update_fields=["limits"])


def remove_key(apps, schema_editor):
    Tier = apps.get_model("member", "Tier")
    for tier in Tier.objects.all():
        limits = tier.limits if isinstance(tier.limits, dict) else {}
        if limits.pop(KEY, None) is None:
            continue
        tier.limits = limits
        tier.save(update_fields=["limits"])


class Migration(migrations.Migration):

    dependencies = [
        ("member", "0018_retire_basic_tier"),
    ]

    operations = [
        migrations.RunPython(add_key, remove_key),
    ]
