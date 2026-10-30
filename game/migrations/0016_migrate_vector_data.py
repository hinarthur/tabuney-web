# game/migrations/xxxx_migrate_vector_data.py

from django.db import migrations

def migrate_vector_data(apps, schema_editor):
    RulebookChunk = apps.get_model('game', 'RulebookChunk')
    RulebookChunkVector = apps.get_model('game', 'RulebookChunkVector')
    
    for vec in RulebookChunkVector.objects.select_related('chunk').iterator():
        if vec.chunk:
            RulebookChunk.objects.filter(pk=vec.chunk_id).update(
                vector_point_id=vec.point_id,
                vector_collection=vec.collection_name,
                embedding_model=vec.embedding_model,
                embedding_version=vec.embedding_version,
                vector_sync_status=vec.sync_status,
                vector_synced_at=vec.synced_at,
                vector_last_error=vec.last_error,
            )

def reverse_migrate(apps, schema_editor):
    pass  # 或實作反向遷移

class Migration(migrations.Migration):
    dependencies = [
        ('game', '0015_add_vector_fields_to_chunk'),
    ]
    
    operations = [
        migrations.RunPython(migrate_vector_data, reverse_migrate),
    ]