from django.db import migrations
from django.contrib.postgres.operations import UnaccentExtension


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0066_rename_package_kind_update_to_variant'),
    ]

    operations = [
        UnaccentExtension(),
    ]
