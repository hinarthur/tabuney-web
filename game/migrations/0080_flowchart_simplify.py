# Drop scope/strategy from RulebookFlowchart; add detail (concise/detailed).
# Wipes existing rows since old combinations no longer apply.

from django.db import migrations, models


def wipe_old_flowcharts(apps, schema_editor):
    RulebookFlowchart = apps.get_model("game", "RulebookFlowchart")
    RulebookFlowchart.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0079_rulebookflowchart"),
    ]

    operations = [
        migrations.RunPython(wipe_old_flowcharts, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="rulebookflowchart",
            name="uq_flowchart_combo",
        ),
        migrations.RemoveIndex(
            model_name="rulebookflowchart",
            name="game_rulebo_ruleboo_b6fe41_idx",
        ),
        migrations.RemoveField(
            model_name="rulebookflowchart",
            name="scope",
        ),
        migrations.RemoveField(
            model_name="rulebookflowchart",
            name="strategy",
        ),
        migrations.AddField(
            model_name="rulebookflowchart",
            name="detail",
            field=models.CharField(
                choices=[("concise", "Concise"), ("detailed", "Detailed")],
                db_index=True,
                default="detailed",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="rulebookflowchart",
            constraint=models.UniqueConstraint(
                fields=("rulebook", "edition", "ruleset", "detail"),
                name="uq_flowchart_detail",
            ),
        ),
        migrations.AddIndex(
            model_name="rulebookflowchart",
            index=models.Index(fields=["rulebook", "detail"], name="game_rulebo_ruleboo_bcfeb3_idx"),
        ),
    ]
