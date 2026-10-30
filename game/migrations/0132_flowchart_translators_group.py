"""
建立 flowchart_translators 群組（給翻譯員）：能查看 rulebook、編輯 Flowchart text
（FlowchartTextTranslation）的譯文，其餘一律唯讀或沒有權限。

不含流程圖本身的 change 權限（改圖是 flowchart_editors）、也不含 delete
（清除未使用譯文的 GC 動作需要 delete 權限，見 FlowchartTextTranslationAdmin）。
使用者還要勾選 is_staff 才登入得了 admin。
"""

from django.db import migrations

GROUP = "flowchart_translators"
PERMS = [
    ("game", "view_rulebook"),
    ("game", "view_edition"),       # Rulebook 頁會顯示所屬 edition
    ("game", "view_flowcharttexttranslation"),
    ("game", "change_flowcharttexttranslation"),
]


def create_group(apps, schema_editor):
    from django.contrib.auth.management import create_permissions
    from django.contrib.contenttypes.management import create_contenttypes

    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_contenttypes(app_config, apps=apps, verbosity=0)
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name=GROUP)
    for app_label, codename in PERMS:
        group.permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )


def remove_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('game', '0131_remove_rulebookflowchart_translation_status'),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
