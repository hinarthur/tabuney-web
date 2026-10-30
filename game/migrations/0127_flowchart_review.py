# 流程圖審核機制（schema 部分）。is_published 的資料要先在 0128 搬進
# FlowchartPublication，0129 才移除欄位。

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('game', '0126_rulebookflowchart_display_order'),
    ]

    operations = [
        migrations.CreateModel(
            name='FlowchartPublication',
            fields=[
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('flowchart', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='publication', serialize=False, to='game.rulebookflowchart')),
                ('content', models.JSONField(default=dict)),
                ('content_hash', models.CharField(max_length=64)),
                ('is_live', models.BooleanField(db_index=True, default=True)),
                ('approved_by_name', models.CharField(blank=True, max_length=150)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterModelOptions(
            name='rulebookflowchart',
            options={'permissions': [('review_rulebookflowchart', 'Can review and publish flowcharts')], 'verbose_name': 'flowchart', 'verbose_name_plural': 'flowcharts'},
        ),
        migrations.AddField(
            model_name='rulebookflowchart',
            name='content_edited_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='rulebookflowchart',
            name='content_edited_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='edited_flowcharts', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='rulebookflowchart',
            name='content_hash',
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=64),
        ),
        migrations.CreateModel(
            name='FlowchartReview',
            fields=[
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action', models.CharField(choices=[('submitted', '送審'), ('approved', '核准發布'), ('rejected', '退回'), ('unpublished', '下架')], db_index=True, max_length=20)),
                ('content_hash', models.CharField(blank=True, max_length=64)),
                ('content', models.JSONField(blank=True, default=None, null=True)),
                ('comment', models.TextField(blank=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='flowchart_review_actions', to=settings.AUTH_USER_MODEL)),
                ('flowchart', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='game.rulebookflowchart')),
                ('last_editor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['flowchart', '-created_at'], name='game_flowch_flowcha_731bb4_idx')],
            },
        ),
    ]
