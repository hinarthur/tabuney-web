from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0080_flowchart_simplify"),
    ]

    operations = [
        migrations.AddField(
            model_name="rulebookflowchart",
            name="react_flow_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="rulebookflowchart",
            name="adjusted_json",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
