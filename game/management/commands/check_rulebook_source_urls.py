import time

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from game.models import Rulebook

# 連續失敗幾次才標 broken，避免對方一時當機就把連結灰掉
BROKEN_AFTER = 2
# 這些狀態碼代表網址確實不在了；其餘 4xx/5xx（403、429、503…）多半是擋機器人或暫時故障
DEAD_STATUS = {404, 410}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TableJourneyLinkCheck/1.0)"}


def probe(url, timeout):
    """回傳 'ok' / 'dead' / 'unknown'。HEAD 不被支援時退回 GET（不下載內容）。"""
    try:
        resp = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code in (403, 405, 501) or resp.status_code >= 500:
            resp = requests.get(
                url, headers=HEADERS, timeout=timeout, allow_redirects=True, stream=True
            )
            resp.close()
    except (requests.ConnectionError, requests.Timeout):
        # DNS 失敗、連線被拒、逾時：算失敗，由連續次數把關
        return "dead"
    except requests.RequestException:
        return "unknown"
    if resp.status_code in DEAD_STATUS:
        return "dead"
    if resp.status_code < 400:
        return "ok"
    return "unknown"


class Command(BaseCommand):
    help = "檢查 Rulebook.source_url 是否仍可開啟，更新 source_url_status"

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=15)
        parser.add_argument("--delay", type=float, default=0.5, help="每筆之間的間隔秒數")
        parser.add_argument("--dry-run", action="store_true", help="只檢查、不寫入")

    def handle(self, *args, **opts):
        qs = Rulebook.objects.exclude(source_url="")
        total = qs.count()
        changed = 0
        for rb in qs.iterator():
            result = probe(rb.source_url, opts["timeout"])
            fails = rb.source_url_fail_count
            if result == "ok":
                status, fails = "ok", 0
            elif result == "dead":
                fails += 1
                status = "broken" if fails >= BROKEN_AFTER else rb.source_url_status
            else:
                # 擋機器人／暫時故障：不算壞，狀態與既有失敗次數都維持原樣
                status = rb.source_url_status
            self.stdout.write(f"{result:8} {status:8} {rb.source_url}")
            if not opts["dry_run"]:
                status_changed = status != rb.source_url_status
                rb.source_url_status = status
                rb.source_url_fail_count = fails
                rb.source_url_checked_at = timezone.now()
                fields = ["source_url_status", "source_url_fail_count", "source_url_checked_at"]
                # 狀態有變才動 updated_at，delta sync 才會把它帶到 VPS
                if status_changed:
                    fields.append("updated_at")
                    changed += 1
                rb.save(update_fields=fields)
            time.sleep(opts["delay"])
        self.stdout.write(self.style.SUCCESS(f"檢查 {total} 筆，狀態變動 {changed} 筆"))
