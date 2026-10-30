# 手寫：makemigrations 在非互動模式把改名判成 Remove+Add（會清掉所有已發布
# 標記）。改用 RenameField 保留現有資料。
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0121_edition_color_vision_friendly'),
    ]

    operations = [
        migrations.RenameField(
            model_name='rulebookflowchart',
            old_name='human_adjust',
            new_name='is_published',
        ),
        migrations.AlterField(
            model_name='rulebookflowchart',
            name='is_published',
            field=models.BooleanField(
                default=False,
                help_text='勾選＝公開發布（未勾選的圖不會出現在公開頁、sitemap，也不會同步到 VPS）',
            ),
        ),
    ]
