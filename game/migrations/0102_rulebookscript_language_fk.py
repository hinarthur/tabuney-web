from django.db import migrations, models
import django.db.models.deletion


def migrate_language_code_to_tribe(apps, schema_editor):
    """把舊 CharField 語言代碼(en/zh/ja/fr/de/es)轉成對應的 Tribe FK。"""
    RulebookScript = apps.get_model('game', 'RulebookScript')
    Tribe = apps.get_model('translation', 'Tribe')

    for obj in RulebookScript.objects.all():
        code = obj.language or 'zh'
        tribe, _ = Tribe.objects.get_or_create(
            language=code, defaults={'name': code},
        )
        obj.language_fk = tribe
        obj.save(update_fields=['language_fk'])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0007_translation_is_synced_translation_synced_at'),
        ('game', '0101_rulebookscript_linked_editions'),
    ]

    operations = [
        migrations.AddField(
            model_name='rulebookscript',
            name='language_fk',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='scripts', to='translation.tribe',
            ),
        ),
        migrations.RunPython(migrate_language_code_to_tribe, reverse_noop),
        migrations.RemoveField(
            model_name='rulebookscript',
            name='language',
        ),
        migrations.RenameField(
            model_name='rulebookscript',
            old_name='language_fk',
            new_name='language',
        ),
        migrations.AlterField(
            model_name='rulebookscript',
            name='language',
            field=models.ForeignKey(
                help_text='講稿輸出語言',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='scripts', to='translation.tribe',
            ),
        ),
    ]
