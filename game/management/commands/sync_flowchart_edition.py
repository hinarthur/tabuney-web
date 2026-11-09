"""把 RulebookFlowchart.edition 修正成與 rulebook.edition 一致。

用法：python manage.py sync_flowchart_edition [--dry-run]
"""
from django.core.management.base import BaseCommand
from django.db.models import F

from game.models import RulebookFlowchart


class Command(BaseCommand):
    help = "修正 flowchart.edition 與 rulebook.edition 不一致的資料"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        qs = RulebookFlowchart.objects.exclude(edition_id=F("rulebook__edition_id"))
        count = qs.count()
        if opts["dry_run"]:
            self.stdout.write(f"不一致 {count} 筆（dry-run，未修改）")
            return
        # queryset.update 不經 save()，不會動 updated_at / content_hash
        for fc in qs.select_related("rulebook"):
            RulebookFlowchart.objects.filter(pk=fc.pk).update(edition_id=fc.rulebook.edition_id)
        self.stdout.write(self.style.SUCCESS(f"已修正 {count} 筆"))
