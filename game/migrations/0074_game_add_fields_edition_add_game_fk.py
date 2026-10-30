"""
Migration 0074: Add new fields to Game, add nullable game FK to Edition.
This is the first step of removing the Package layer.
Step 2 (data migration) is in 0075.
Step 3 (cleanup) is in 0076.
"""
import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0073_remove_rulebook_game_rulebo_edition_77ae78_idx_and_more"),
    ]

    operations = [
        # 1. Add Kind field + player/playtime + parent_game to Game
        migrations.AddField(
            model_name="game",
            name="kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("standalone", "Standalone"),
                    ("expansion", "Expansion"),
                    ("variant", "Variant"),
                    ("bundle", "Bundle"),
                ],
                max_length=20,
                null=True,
                help_text="產品類型：基本版 / 擴充 / 變體 / 套裝",
            ),
        ),
        migrations.AddField(
            model_name="game",
            name="min_players",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="game",
            name="max_players",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="game",
            name="min_playtime",
            field=models.PositiveSmallIntegerField(blank=True, null=True, help_text="minutes"),
        ),
        migrations.AddField(
            model_name="game",
            name="max_playtime",
            field=models.PositiveSmallIntegerField(blank=True, null=True, help_text="minutes"),
        ),
        migrations.AddField(
            model_name="game",
            name="parent_game",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="children",
                to="game.game",
                help_text="擴充/變體指向依賴的主 Game",
            ),
        ),
        # 2. Add nullable game FK to Edition (will be made NOT NULL in 0076 after data migration)
        migrations.AddField(
            model_name="edition",
            name="game",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="editions",
                to="game.game",
            ),
        ),
        # 3. Remove Rulebook.play_mode FK (PlayMode being removed)
        migrations.RemoveField(
            model_name="rulebook",
            name="play_mode",
        ),
    ]
