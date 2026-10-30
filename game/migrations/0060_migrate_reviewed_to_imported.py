# Generated manually to migrate reviewed status to imported

from django.db import migrations


def migrate_reviewed_to_imported(apps, schema_editor):
    """Convert all ScrapedProduct records with status='reviewed' to 'imported'"""
    ScrapedProduct = apps.get_model('game', 'ScrapedProduct')
    
    # Update all records with status='reviewed' to 'imported'
    ScrapedProduct.objects.filter(status='reviewed').update(status='imported')


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0059_entity_scrape_batch_size_entity_scrape_page_start'),
    ]

    operations = [
        migrations.RunPython(migrate_reviewed_to_imported, migrations.RunPython.noop),
    ]
