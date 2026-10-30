from django.db import migrations


def backfill_cq(apps, schema_editor):
    Game = apps.get_model('game', 'Game')
    for game in Game.objects.all().iterator():
        values = [
            getattr(game, field) or 0
            for field in (
                'problem_solving', 'collaboration', 'adaptability',
                'critical_thinking', 'communication', 'creativity',
            )
        ]
        sumsq = sum((5 - v) ** 2 for v in values)
        game.cq = 5 - (sumsq / len(values)) ** 0.5
        game.save(update_fields=['cq'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0096_game_cq'),
    ]

    operations = [
        migrations.RunPython(backfill_cq, noop),
    ]
