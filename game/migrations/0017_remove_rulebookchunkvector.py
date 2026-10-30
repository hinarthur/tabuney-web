# game/migrations/xxxx_remove_rulebookchunkvector.py

from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('game', '0016_migrate_vector_data'),
    ]
    
    operations = [
        migrations.DeleteModel(name='RulebookChunkVector'),
    ]