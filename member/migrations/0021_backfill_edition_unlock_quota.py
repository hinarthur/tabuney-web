"""新 tier feature 'edition_unlock'（免費永久解鎖名額）寫進既有 Tier.limits。

registry default 已經是 3，所以不回填也不會有人失去權益——回填的目的純粹是
讓這個 key 出現在 Tier admin 的表單與 limits_summary 裡，營運才調得動。
（TierLimitsForm 是依 registry 產生欄位，但 limits_summary 顯示的是 DB 實際
存的值，沒有這個 key 會顯示成 None。）

只補「還沒有這個 key」的 tier，不覆蓋後台已經手動調過的值。所有 tier 一律給
同樣的名額：免費名額是註冊送的，與付費等級無關（subscriber 也有，讓他日後
會籍過期時仍保有這 3 款）。
"""

from django.db import migrations

KEY = "edition_unlock"
DEFAULT = 3


def add_key(apps, schema_editor):
    Tier = apps.get_model("member", "Tier")
    for tier in Tier.objects.all():
        limits = tier.limits if isinstance(tier.limits, dict) else {}
        if KEY in limits:
            continue
        limits[KEY] = DEFAULT
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
        ("member", "0020_editionunlock_and_more"),
    ]

    operations = [
        migrations.RunPython(add_key, remove_key),
    ]
