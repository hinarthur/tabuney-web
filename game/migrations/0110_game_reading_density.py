"""
read_load 更名為 reading_density，並重新定義級距：
none / minimal_text / full_sentences / extended_text
  →  none / labels       / simple         / complex

RenameField 保留既有資料，RunPython 再把舊值換成新值。
"""

from django.db import migrations, models

VALUE_MAP = {
    'minimal_text':   'labels',
    'full_sentences': 'simple',
    'extended_text':  'complex',
}


def forwards(apps, schema_editor):
    Game = apps.get_model('game', 'Game')
    for old, new in VALUE_MAP.items():
        Game.objects.filter(reading_density=old).update(reading_density=new)


def backwards(apps, schema_editor):
    Game = apps.get_model('game', 'Game')
    for old, new in VALUE_MAP.items():
        Game.objects.filter(reading_density=new).update(reading_density=old)


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0109_gamesuggestion_barcode'),
    ]

    operations = [
        migrations.RenameField(
            model_name='game',
            old_name='read_load',
            new_name='reading_density',
        ),
        migrations.AlterField(
            model_name='game',
            name='reading_density',
            field=models.CharField(
                blank=True,
                choices=[('none', 'None'), ('labels', 'Labels'),
                         ('simple', 'Simple'), ('complex', 'Complex')],
                help_text='Reading density in the game components（不計cue cards或rulebook）',
                max_length=20,
                null=True,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
