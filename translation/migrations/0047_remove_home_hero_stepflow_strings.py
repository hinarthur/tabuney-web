"""
hero 的 Step Flow 改用流程圖頁的 game.flowchart.tour.* 字串後，
0042 為它新增的這幾組不再有人用，刪掉。
"""

from django.db import migrations

OBSOLETE_KEYS = [
    'home.hero.caption_branch',
    'home.hero.caption_sequence',
    'home.hero.caption_end',
    'home.hero.nav_first',
    'home.hero.nav_prev',
    'home.hero.nav_next',
    'home.hero.nav_last',
]


def remove_strings(apps, schema_editor):
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(key__in=OBSOLETE_KEYS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0046_home_guides_browse_card'),
    ]

    # 反向不還原：需要時重跑 0042 即可補回
    operations = [
        migrations.RunPython(remove_strings, migrations.RunPython.noop),
    ]
