import os
import shutil

from django.core.management.base import BaseCommand
from django.db import transaction

from game.models import Rulebook


def _new_rulebook_pdf_name(rulebook: Rulebook) -> str:
    rb_id = rulebook.id
    rb_hex = rb_id.hex
    return f"rulebooks/{rb_hex[:2]}/{rb_hex[2:4]}/{rb_id}.pdf"


class Command(BaseCommand):
    help = "Migrate Rulebook PDFs to rulebooks/<uuid[:2]>/<uuid[2:4]>/<uuid>.pdf"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print what would change; do not move files or update DB.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit how many Rulebooks to process (for testing).",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        limit = options.get("limit")

        qs = Rulebook.objects.exclude(file="").exclude(file__isnull=True).order_by("created_at")
        if limit:
            qs = qs[:limit]

        moved = 0
        skipped = 0
        missing = 0
        conflicts = 0
        failed = 0

        for rb in qs.iterator(chunk_size=200):
            old_name = rb.file.name
            new_name = _new_rulebook_pdf_name(rb)

            if not old_name:
                skipped += 1
                continue

            if old_name == new_name:
                skipped += 1
                continue

            storage = rb.file.storage

            old_exists = storage.exists(old_name)
            new_exists = storage.exists(new_name)

            if new_exists and not old_exists:
                # DB 指到舊路徑、但檔案已在新位置（或舊檔被手動刪除）
                if dry_run:
                    self.stdout.write(f"[DRY] fix db: {rb.id} {old_name} -> {new_name}")
                else:
                    rb.file.name = new_name
                    rb.save(update_fields=["file", "updated_at"])
                moved += 1
                continue

            if not old_exists:
                self.stdout.write(self.style.WARNING(f"[MISS] {rb.id} file missing: {old_name}"))
                missing += 1
                continue

            if new_exists:
                self.stdout.write(self.style.WARNING(
                    f"[CONFLICT] {rb.id} new path exists, skip move: {new_name} (old={old_name})"
                ))
                conflicts += 1
                continue

            if dry_run:
                self.stdout.write(f"[DRY] move: {old_name} -> {new_name}")
                moved += 1
                continue

            try:
                # Prefer true move on local filesystem storage
                if hasattr(storage, "path"):
                    old_path = storage.path(old_name)
                    new_path = storage.path(new_name)
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    shutil.move(old_path, new_path)
                else:
                    # Fallback: copy via storage API then delete old
                    with storage.open(old_name, "rb") as f:
                        storage.save(new_name, f)
                    storage.delete(old_name)

                with transaction.atomic():
                    rb.file.name = new_name
                    rb.save(update_fields=["file", "updated_at"])

                moved += 1
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"[FAIL] {rb.id} {old_name} -> {new_name}: {exc}"))

        self.stdout.write(
            "\n".join(
                [
                    "Done.",
                    f"  moved/fixed: {moved}",
                    f"  skipped:     {skipped}",
                    f"  missing:     {missing}",
                    f"  conflicts:   {conflicts}",
                    f"  failed:      {failed}",
                ]
            )
        )

