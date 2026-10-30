"""
把 django.contrib.sites 的 Site 列從預設的 example.com 改成正式網域。

django.contrib.sitemaps 用 get_current_site() 組出 sitemap 裡的絕對網址，
不修的話整份 sitemap.xml 會指向 http://example.com/…。allauth 也讀這一列。
"""

import os

from django.conf import settings
from django.db import migrations

DEFAULT_DOMAIN = "tabuney.com"
DEFAULT_NAME = "Tabuney"


def set_site_domain(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    domain = os.getenv("SITE_DOMAIN", DEFAULT_DOMAIN)
    Site.objects.update_or_create(
        pk=settings.SITE_ID,
        defaults={"domain": domain, "name": DEFAULT_NAME},
    )


def restore_example_com(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    Site.objects.filter(pk=settings.SITE_ID).update(
        domain="example.com", name="example.com",
    )


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [
        migrations.RunPython(set_site_domain, restore_example_com),
    ]
