"""
流程圖審核機制（資料部分）：
  1. 每張圖補上 content_hash
  2. 原本 is_published=True 的圖：建立 FlowchartPublication（內容＝當下的
     effective JSON）與一筆 approved 審核紀錄，公開頁看到的內容不變
  3. 建立 flowchart_editors / flowchart_reviewers 兩個群組

本機與 VPS 各自執行；VPS 上的已發布圖就是同步過去的那批，結果一致。
"""

from django.db import migrations
from django.utils import timezone

EDITORS = "flowchart_editors"
REVIEWERS = "flowchart_reviewers"

EDITOR_PERMS = [
    ("game", "view_rulebookflowchart"),
    ("game", "change_rulebookflowchart"),
    ("game", "view_flowchartreview"),
    ("game", "view_rulebook"),
    ("game", "view_edition"),
]
REVIEWER_PERMS = [
    ("game", "view_rulebookflowchart"),
    ("game", "review_rulebookflowchart"),
    ("game", "view_flowchartreview"),
    ("game", "view_rulebook"),
    ("game", "view_edition"),
]


def _effective(chart):
    return chart.adjusted_json or chart.react_flow_json or {}


def forwards(apps, schema_editor):
    from game.models import flowchart_content_hash

    RulebookFlowchart = apps.get_model("game", "RulebookFlowchart")
    FlowchartPublication = apps.get_model("game", "FlowchartPublication")
    FlowchartReview = apps.get_model("game", "FlowchartReview")

    now = timezone.now()
    for chart in RulebookFlowchart.objects.all().iterator():
        content = _effective(chart)
        content_hash = flowchart_content_hash(content)
        # update() 不會動 updated_at，避免整批圖在下次 delta sync 被重送
        RulebookFlowchart.objects.filter(pk=chart.pk).update(content_hash=content_hash)
        if not chart.is_published or not content:
            continue
        FlowchartPublication.objects.create(
            flowchart_id=chart.pk,
            content=content,
            content_hash=content_hash,
            is_live=True,
            approved_by_name="(migrated)",
            approved_at=now,
        )
        FlowchartReview.objects.create(
            flowchart_id=chart.pk,
            action="approved",
            content_hash=content_hash,
            content=content,
            comment="審核機制上線前已發布",
        )


def create_groups(apps, schema_editor):
    # 自訂權限（review_rulebookflowchart）與新 model 的 view 權限平常要等
    # post_migrate 才會建立，這裡先手動建好才能指派給群組。
    from django.contrib.auth.management import create_permissions
    from django.contrib.contenttypes.management import create_contenttypes

    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_contenttypes(app_config, apps=apps, verbosity=0)
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for name, perms in ((EDITORS, EDITOR_PERMS), (REVIEWERS, REVIEWER_PERMS)):
        group, _ = Group.objects.get_or_create(name=name)
        for app_label, codename in perms:
            perm = Permission.objects.get(content_type__app_label=app_label, codename=codename)
            group.permissions.add(perm)


def backwards(apps, schema_editor):
    RulebookFlowchart = apps.get_model("game", "RulebookFlowchart")
    FlowchartPublication = apps.get_model("game", "FlowchartPublication")
    live_ids = FlowchartPublication.objects.filter(is_live=True).values_list("flowchart_id", flat=True)
    RulebookFlowchart.objects.filter(pk__in=list(live_ids)).update(is_published=True)
    FlowchartPublication.objects.all().delete()
    apps.get_model("game", "FlowchartReview").objects.all().delete()
    apps.get_model("auth", "Group").objects.filter(name__in=[EDITORS, REVIEWERS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('game', '0127_flowchart_review'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.RunPython(create_groups, migrations.RunPython.noop),
    ]
