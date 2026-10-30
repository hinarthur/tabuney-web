"""
建立 VPS 負荷採樣的 django-q 排程（每 10 分鐘）。

寫成 migration 而不是叫人去 admin 手動新增：部署時 migrate 就會建好，
本機與正式站一致。get_or_create 讓重跑也安全。
"""

from django.db import migrations

SCHEDULE_NAME = 'stats: sample_server'


def create_schedule(apps, schema_editor):
    Schedule = apps.get_model('django_q', 'Schedule')
    Schedule.objects.get_or_create(
        name=SCHEDULE_NAME,
        defaults={
            'func': 'stats.tasks.sample_server',
            'schedule_type': 'I',  # Schedule.MINUTES
            'minutes': 10,
            'repeats': -1,
        },
    )


def delete_schedule(apps, schema_editor):
    Schedule = apps.get_model('django_q', 'Schedule')
    Schedule.objects.filter(name=SCHEDULE_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('stats', '0010_serversample_erroralertack'),
        ('django_q', '0014_schedule_cluster'),
    ]

    operations = [
        migrations.RunPython(create_schedule, delete_schedule),
    ]
