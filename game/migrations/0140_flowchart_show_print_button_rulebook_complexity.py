import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0139_flowchartsuggestion_node_id_and_more'),
    ]

    operations = [
        # 先以 True 加欄位讓既有的圖全部顯示，再把預設改回 False（新圖預設不顯示）
        migrations.AddField(
            model_name='rulebookflowchart',
            name='show_print_button',
            field=models.BooleanField(default=True, help_text='勾選＝流程圖瀏覽頁顯示 A4 列印按鈕'),
        ),
        migrations.AlterField(
            model_name='rulebookflowchart',
            name='show_print_button',
            field=models.BooleanField(default=False, help_text='勾選＝流程圖瀏覽頁顯示 A4 列印按鈕'),
        ),
        migrations.AddField(
            model_name='rulebook',
            name='complexity',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='規則書複雜度，1~999',
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(999),
                ],
            ),
        ),
    ]
