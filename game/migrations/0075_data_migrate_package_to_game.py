"""
Migration 0075: Data migration — promote each Package to a Game entry.

Logic:
- Games with exactly 1 Package → copy fields directly to existing Game
- Games with multiple Packages:
  - The STANDALONE Package (if any) stays on the existing Game
  - Other Packages become new Game entries with parent_game → original Game
  - If no STANDALONE exists, the first Package (by created_at) keeps the original Game
- Edition.game_id is filled from the resolved target Game
- Orphan Packages (no editions) are assigned to their parent Game directly
"""
import uuid
from django.db import migrations


def migrate_packages_to_games(apps, schema_editor):
    Game = apps.get_model("game", "Game")
    Package = apps.get_model("game", "Package")
    Edition = apps.get_model("game", "Edition")
    GameTitle = apps.get_model("game", "GameTitle")

    db_alias = schema_editor.connection.alias

    # Build a map: game_id → list of packages
    from collections import defaultdict
    game_to_packages = defaultdict(list)
    for pkg in Package.objects.using(db_alias).select_related("game").order_by("created_at"):
        game_to_packages[str(pkg.game_id)].append(pkg)

    # Map: package_id → target_game_id (for Edition assignment)
    pkg_to_game = {}

    for game_id, packages in game_to_packages.items():
        original_game = Game.objects.using(db_alias).get(id=game_id)

        if len(packages) == 1:
            # Simple case: 1 Package per Game
            pkg = packages[0]
            original_game.kind = pkg.kind
            original_game.min_players = pkg.min_players
            original_game.max_players = pkg.max_players
            original_game.min_playtime = pkg.min_playtime
            original_game.max_playtime = pkg.max_playtime
            original_game.save(using=db_alias, update_fields=[
                "kind", "min_players", "max_players",
                "min_playtime", "max_playtime",
            ])
            pkg_to_game[str(pkg.id)] = str(original_game.id)

        else:
            # Multiple Packages: determine which Package keeps the original Game
            # Priority: STANDALONE → first package by created_at
            primary_pkg = None
            for p in packages:
                if p.kind == "standalone":
                    primary_pkg = p
                    break
            if primary_pkg is None:
                primary_pkg = packages[0]

            for pkg in packages:
                if pkg == primary_pkg:
                    # This package keeps the original Game
                    original_game.kind = pkg.kind
                    original_game.min_players = pkg.min_players
                    original_game.max_players = pkg.max_players
                    original_game.min_playtime = pkg.min_playtime
                    original_game.max_playtime = pkg.max_playtime
                    original_game.save(using=db_alias, update_fields=[
                        "kind", "min_players", "max_players",
                        "min_playtime", "max_playtime",
                    ])
                    pkg_to_game[str(pkg.id)] = str(original_game.id)
                else:
                    # Create a new Game for this Package
                    new_game = Game(
                        id=uuid.uuid4(),
                        canonical_name=pkg.name,
                        bgg_id=None,
                        kind=pkg.kind,
                        min_players=pkg.min_players,
                        max_players=pkg.max_players,
                        min_playtime=pkg.min_playtime,
                        max_playtime=pkg.max_playtime,
                        parent_game=original_game,
                        # Inherit some attributes from parent
                        affiliate=original_game.affiliate,
                    )
                    new_game.save(using=db_alias)
                    pkg_to_game[str(pkg.id)] = str(new_game.id)

                    # Copy GameTitle from original game as a reference (optional, skip if too noisy)
                    # Not copying titles — the new Game entry's canonical_name is the package name

    # Now fill Edition.game_id
    for edition in Edition.objects.using(db_alias).select_related("package").all():
        pkg_id = str(edition.package_id)
        target_game_id = pkg_to_game.get(pkg_id)
        if target_game_id:
            edition.game_id = target_game_id
            edition.save(using=db_alias, update_fields=["game"])
        else:
            # Orphan edition (package not in our map — shouldn't happen)
            # Fall back to the package's game
            edition.game_id = str(edition.package.game_id)
            edition.save(using=db_alias, update_fields=["game"])


def reverse_migrate(apps, schema_editor):
    # Reversing this data migration is complex; just clear Edition.game fields
    Edition = apps.get_model("game", "Edition")
    Edition.objects.using(schema_editor.connection.alias).update(game=None)


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0074_game_add_fields_edition_add_game_fk"),
    ]

    operations = [
        migrations.RunPython(migrate_packages_to_games, reverse_migrate),
    ]
