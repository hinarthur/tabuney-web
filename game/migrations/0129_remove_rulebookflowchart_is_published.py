# 公開閘門改由 FlowchartPublication 決定（見 0128 的資料搬移）。

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0128_flowchart_review_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='rulebookflowchart',
            name='is_published',
        ),
    ]
