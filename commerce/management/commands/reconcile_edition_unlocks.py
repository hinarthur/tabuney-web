"""找出「收了錢但沒拿到解鎖」的 US$1 加購。

付了錢沒拿到東西是這個功能最不能靜默的失敗模式，而 stripe_webhook 的外層
blanket except 正好會把它變靜默（log 有，但沒人會去翻）。這支指令從 Stripe
那邊回頭對帳，比對本地的 EditionUnlock。

    python manage.py reconcile_edition_unlocks              # 只列出，不動資料
    python manage.py reconcile_edition_unlocks --fix        # 補建缺少的解鎖
    python manage.py reconcile_edition_unlocks --days 30    # 往回看幾天（預設 7）

判斷依據是 Stripe checkout session 的 metadata.kind == 'edition_unlock'——那是
建立 session 時寫進去的，見 commerce.views.create_edition_unlock_session。
只看 payment_status == 'paid' 的 session：未付款的當然不該有解鎖。
"""

import datetime

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand

from commerce.views import EDITION_UNLOCK_KIND, _ensure_transaction
from member.models import EditionUnlock, Member


class Command(BaseCommand):
    help = "對帳 US$1 Edition 加購：列出付了錢卻沒有對應 EditionUnlock 的訂單"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7, help="往回看幾天（預設 7）")
        parser.add_argument(
            "--fix", action="store_true",
            help="補建缺少的 EditionUnlock（預設只列出，不動資料）",
        )

    def handle(self, *args, **options):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        days = options["days"]
        fix = options["fix"]

        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        created_filter = {"gte": int(since.timestamp())}

        checked = 0
        missing = []

        # auto_paging_iter 會自己翻頁；範圍以天數控制，不要一次撈全部歷史。
        for session in stripe.checkout.Session.list(
            created=created_filter, limit=100,
        ).auto_paging_iter():
            meta = session.get("metadata") or {}
            if meta.get("kind") != EDITION_UNLOCK_KIND:
                continue
            if session.get("payment_status") != "paid":
                continue

            checked += 1
            edition_id = meta.get("edition_id")
            member_id = session.get("client_reference_id")
            if not edition_id or not member_id:
                missing.append((session["id"], member_id, edition_id, "metadata 不完整"))
                continue

            member = Member.objects.filter(pk=member_id).first()
            if member is None:
                missing.append((session["id"], member_id, edition_id, "查無此 Member"))
                continue

            if EditionUnlock.objects.filter(
                member=member, edition_id=edition_id,
            ).exists():
                continue

            missing.append((session["id"], member_id, edition_id, "缺少解鎖"))

            if fix:
                # 與 webhook、成功頁共用同一個函式：補建的解鎖要連交易紀錄一起
                # 建立（以前只在已存在時才掛上，webhook 沒到的那種就是 None）。
                txn = _ensure_transaction(session, member)
                EditionUnlock.objects.get_or_create(
                    member=member, edition_id=edition_id,
                    defaults={
                        "source": EditionUnlock.Source.PAID,
                        "transaction": txn,
                    },
                )

        self.stdout.write(f"檢查了 {checked} 筆已付款的 edition_unlock session（近 {days} 天）")
        if not missing:
            self.stdout.write(self.style.SUCCESS("全部都有對應的解鎖，無需處理。"))
            return

        self.stdout.write(self.style.WARNING(f"有 {len(missing)} 筆有問題："))
        for session_id, member_id, edition_id, reason in missing:
            self.stdout.write(
                f"  {session_id}  member={member_id}  edition={edition_id}  → {reason}"
            )
        if fix:
            self.stdout.write(self.style.SUCCESS("已補建可補的解鎖（metadata 不完整或查無 Member 的仍需人工處理）。"))
        else:
            self.stdout.write("加上 --fix 可自動補建。")
