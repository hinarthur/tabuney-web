from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0133_edition_import_permission"),
    ]

    operations = [
        migrations.AddField(
            model_name="rulebook",
            name="source_url_status",
            field=models.CharField(
                choices=[("unknown", "Unknown"), ("ok", "OK"), ("broken", "Broken")],
                default="unknown",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="rulebook",
            name="source_url_fail_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="rulebook",
            name="source_url_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
