"""
替 result_count / matched_by / input_kind 上線前的舊 SearchLog 補資料。

語意是「用今天的資料庫回頭看，這些歷史搜尋還是找不到嗎」—— 補完之後，
admin 首頁的「該補的作品」清單就會涵蓋歷史，不必等新資料慢慢累積。

    python manage.py backfill_search_meta --dry-run
    python manage.py backfill_search_meta
"""

from django.core.management.base import BaseCommand

from game.selectors import search_editions
from stats.models import SearchLog
from stats.utils import guess_input_kind

BATCH_SIZE = 500


class Command(BaseCommand):
    help = '回填舊 SearchLog 的 result_count / matched_by / input_kind / is_bot'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='只統計會改幾筆，不寫入資料庫',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # 只處理沒跑過的：matched_by 為空就是本次上線前寫入的
        rows = list(SearchLog.objects.filter(matched_by='').order_by('id'))
        if not rows:
            self.stdout.write(self.style.SUCCESS('沒有需要回填的資料。'))
            return

        self.stdout.write(f'待回填 {len(rows)} 筆…')

        # 同一個關鍵字只查一次資料庫
        cache = {}
        for row in rows:
            keyword = (row.keyword or '').strip()

            row.input_kind = guess_input_kind(keyword)
            # 舊資料沒留 User-Agent，只能靠關鍵字形狀判斷
            # （爬蟲把 JSON-LD 樣板字面 {search_term_string} 送進來）
            if '{' in keyword:
                row.is_bot = True

            if keyword not in cache:
                result = search_editions(keyword)
                cache[keyword] = (result.editions.count(), result.matched_by)
            row.result_count, row.matched_by = cache[keyword]

        missing = sum(1 for r in rows if r.result_count == 0 and not r.is_bot)
        bots = sum(1 for r in rows if r.is_bot)
        self.stdout.write(
            f'不重複關鍵字 {len(cache)} 個｜判定為爬蟲 {bots} 筆｜'
            f'真人未命中 {missing} 筆'
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('dry-run，未寫入資料庫。'))
            return

        SearchLog.objects.bulk_update(
            rows,
            ['result_count', 'matched_by', 'input_kind', 'is_bot'],
            batch_size=BATCH_SIZE,
        )
        self.stdout.write(self.style.SUCCESS(f'已回填 {len(rows)} 筆。'))
