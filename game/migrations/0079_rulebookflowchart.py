# Generated for RulebookFlowchart on 2026-05-08

import uuid
import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0078_alter_scrapedproduct_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='RulebookFlowchart',
            fields=[
                ('created_at', models.DateTimeField(default=timezone.now, editable=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ruleset', models.CharField(db_index=True, default='basic', max_length=100)),
                ('scope', models.CharField(choices=[('lifecycle', 'Lifecycle'), ('sequence', 'Sequence')], max_length=20)),
                ('strategy', models.CharField(choices=[('structured', 'Structured'), ('hybrid', 'Hybrid')], max_length=20)),
                ('mermaid_text', models.TextField(blank=True)),
                ('intermediate_json', models.JSONField(blank=True, default=dict)),
                ('source_chunk_ids', models.JSONField(blank=True, default=list)),
                ('llm_model', models.CharField(blank=True, max_length=100)),
                ('prompt_version', models.CharField(default='v1', max_length=20)),
                ('generation_metadata', models.JSONField(blank=True, default=dict)),
                ('edition', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='flowcharts', to='game.edition')),
                ('rulebook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='flowcharts', to='game.rulebook')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddIndex(
            model_name='rulebookflowchart',
            index=models.Index(fields=['rulebook', 'scope', 'strategy'], name='game_rulebo_ruleboo_b6fe41_idx'),
        ),
        migrations.AddConstraint(
            model_name='rulebookflowchart',
            constraint=models.UniqueConstraint(
                fields=('rulebook', 'edition', 'ruleset', 'scope', 'strategy'),
                name='uq_flowchart_combo',
            ),
        ),
    ]
