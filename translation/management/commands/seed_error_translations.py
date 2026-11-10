from django.core.management.base import BaseCommand

from home.error_views import MESSAGES
from translation.models import Translation, Tribe


class Command(BaseCommand):
    help = "把錯誤頁（error.*）的文案寫進 Translation 表。只補缺的 key，不覆蓋已被編輯的值。"

    def handle(self, *args, **opts):
        created = 0
        for lang, table in MESSAGES.items():
            tribe = Tribe.objects.filter(language=lang).first()
            if not tribe:
                self.stderr.write(f"略過 {lang}：找不到對應的 Tribe")
                continue
            for key, value in table.items():
                _, new = Translation.objects.get_or_create(tribe=tribe, key=key, defaults={'value': value})
                created += new
        self.stdout.write(self.style.SUCCESS(f"新增 {created} 筆"))
