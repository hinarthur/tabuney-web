from django.db import migrations


class Migration(migrations.Migration):
    """
    Restore the DB-level DEFAULT false on human_adjust.

    Django's AddField drops the column default after adding it, leaving only
    the Python-level default.  A stale worker process (e.g. qcluster started
    before the column was added) doesn't know about the field and omits it from
    INSERT statements, causing a NOT NULL violation.  Setting the DB default
    makes inserts safe even from processes running old code.
    """

    dependencies = [
        ('game', '0084_add_human_adjust_to_rulebookflowchart'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE game_rulebookflowchart ALTER COLUMN human_adjust SET DEFAULT false;",
            reverse_sql="ALTER TABLE game_rulebookflowchart ALTER COLUMN human_adjust DROP DEFAULT;",
        ),
    ]
