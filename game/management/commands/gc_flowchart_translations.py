from django.core.management.base import BaseCommand

from game.rag.flowchart.i18n import gc_translations


class Command(BaseCommand):
    help = "GC：刪除沒有任何圖表引用的孤兒 FlowchartTextTranslation row"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只報告會刪幾筆，不實際刪除",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        res = gc_translations(dry_run=dry_run)
        self.stdout.write(
            f"總計 {res['total']} 筆；在用 {res['in_use']} 段；孤兒 {res['orphans']} 筆。"
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"[DRY RUN] 將刪除 {res['orphans']} 筆（未實際刪除）")
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"已刪除 {res['deleted']} 筆孤兒譯文"))
