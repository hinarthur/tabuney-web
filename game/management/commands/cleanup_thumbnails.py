import os
from django.core.management.base import BaseCommand
from django.conf import settings
from game.models import Edition

class Command(BaseCommand):
    help = 'Find and delete orphan thumbnail files in media/edition_thumbnails/'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show which files would be deleted without actually deleting them',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'edition_thumbnails')
        
        if not os.path.exists(thumbnail_dir):
            self.stdout.write(self.style.WARNING(f"Directory {thumbnail_dir} does not exist."))
            return

        # Get all thumbnail paths from the database
        # Edition.thumbnail stores the path relative to MEDIA_ROOT (e.g. 'edition_thumbnails/2026/04/...')
        db_thumbnails = set(Edition.objects.exclude(thumbnail='').values_list('thumbnail', flat=True))
        
        # Convert to absolute paths for comparison, but better to compare relative paths
        # as that's what's stored in the DB.
        
        files_on_disk = []
        for root, dirs, files in os.walk(thumbnail_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, settings.MEDIA_ROOT)
                # Normalize path for DB comparison (Django uses forward slashes)
                rel_path = rel_path.replace(os.sep, '/')
                files_on_disk.append((abs_path, rel_path))

        orphan_files = []
        for abs_path, rel_path in files_on_disk:
            if rel_path not in db_thumbnails:
                orphan_files.append(abs_path)

        if not orphan_files:
            self.stdout.write(self.style.SUCCESS("No orphan thumbnails found."))
            return

        self.stdout.write(f"Found {len(orphan_files)} orphan thumbnail(s):")
        for f in orphan_files:
            if dry_run:
                self.stdout.write(self.style.NOTICE(f"[DRY RUN] Would delete: {f}"))
            else:
                try:
                    os.remove(f)
                    self.stdout.write(self.style.SUCCESS(f"Deleted: {f}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to delete {f}: {e}"))

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Total orphan files: {len(orphan_files)} (None deleted - dry run)"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Total deleted files: {len(orphan_files)}"))
