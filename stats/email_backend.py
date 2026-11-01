"""SMTP 後端：照常寄信，並為每封成功寄出的信記一列 EmailLog，給 admin 的用量圖用。"""

import logging

from django.core.mail.backends.smtp import EmailBackend

logger = logging.getLogger(__name__)


class LoggingSMTPBackend(EmailBackend):
    def _send(self, email_message):
        sent = super()._send(email_message)
        if sent:
            # 記錄失敗絕不能讓寄信失敗：信已經寄出去了，用戶不該因為統計表出問題而看到錯誤。
            try:
                from stats.models import EmailLog
                EmailLog.objects.create(
                    recipient_count=len(email_message.recipients()) or 1,
                    subject=(email_message.subject or '')[:200],
                )
            except Exception:
                logger.exception('EmailLog write failed')
        return sent
