"""
Migration 0076: Schema cleanup after data migration.
- Make Edition.game NOT NULL
- Remove Edition.package FK
- Update Edition constraints and indexes
- Drop Package, PackageDependency, PlayMode, PlayModePackage tables
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0075_data_migrate_package_to_game"),
    ]

    operations = [
        # 1. Remove old Edition unique constraint (package, language, name)
        migrations.RemoveConstraint(
            model_name="edition",
            name="uq_package_language_name",
        ),
        # 2. Remove old Edition indexes on package
        migrations.RemoveIndex(
            model_name="edition",
            name="game_editio_package_1af24a_idx",
        ),
        migrations.RemoveIndex(
            model_name="edition",
            name="game_editio_package_ca4e42_idx",
        ),
        # 3. Make Edition.game NOT NULL (data already filled in 0075)
        migrations.AlterField(
            model_name="edition",
            name="game",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="editions",
                to="game.game",
            ),
        ),
        # 4. Add new Edition unique constraint (game, language, name)
        migrations.AddConstraint(
            model_name="edition",
            constraint=models.UniqueConstraint(
                fields=["game", "language", "name"],
                name="uq_game_language_name",
            ),
        ),
        # 5. Add new Edition indexes on game
        migrations.AddIndex(
            model_name="edition",
            index=models.Index(fields=["game", "language"], name="game_editio_game_id_lang_idx"),
        ),
        migrations.AddIndex(
            model_name="edition",
            index=models.Index(fields=["game", "is_primary"], name="game_editio_game_id_prim_idx"),
        ),
        # 6. Remove Edition.package FK
        migrations.RemoveField(
            model_name="edition",
            name="package",
        ),
        # 7. Drop PlayModePackage (through table, must go before PlayMode and Package)
        migrations.DeleteModel(
            name="PlayModePackage",
        ),
        # 8. Drop PlayMode
        migrations.DeleteModel(
            name="PlayMode",
        ),
        # 9. Drop PackageDependency
        migrations.DeleteModel(
            name="PackageDependency",
        ),
        # 10. Drop Package
        migrations.DeleteModel(
            name="Package",
        ),
    ]
