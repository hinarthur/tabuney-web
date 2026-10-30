from django.db import migrations, models


def backfill_initial(apps, schema_editor):
    """
    既有資料維持原本的付費線：以前免費看得到的是 ruleset="basic"，
    其餘 ruleset 一律鎖住。欄位 default=True 只適用於「之後新建」的圖，
    若不回填，既有的付費 ruleset 會在上線瞬間全部變成免費。
    """
    RulebookFlowchart = apps.get_model("game", "RulebookFlowchart")
    RulebookFlowchart.objects.exclude(ruleset="basic").update(initial=False)


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0118_flowchartsuggestion"),
    ]

    operations = [
        migrations.AddField(
            model_name="rulebookflowchart",
            name="initial",
            field=models.BooleanField(
                default=True,
                db_index=True,
                help_text="勾選＝入門圖，一般會員／未登入者可看內容；取消勾選＝只有 subscriber（含 admin）看得到",
            ),
        ),
        migrations.RunPython(backfill_initial, migrations.RunPython.noop),
    ]
