from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import EmailLog
from .reports import email_usage


def log_emails(count, recipients=1):
    EmailLog.objects.bulk_create([EmailLog(recipient_count=recipients, subject='t') for _ in range(count)])


@override_settings(EMAIL_DAILY_LIMIT=100, EMAIL_MONTHLY_LIMIT=3000)
class EmailUsageTests(TestCase):
    def test_empty_is_ok_and_has_a_full_30_day_series(self):
        usage = email_usage()
        self.assertEqual(usage['level'], 'ok')
        self.assertEqual(usage['today'], 0)
        self.assertEqual(len(usage['daily']), 30)
        self.assertIsNone(usage['peak'])
        self.assertIsNone(usage['tracking_since'])

    def test_each_recipient_counts_as_one_email(self):
        log_emails(2, recipients=3)
        self.assertEqual(email_usage()['today'], 6)

    def test_daily_thresholds(self):
        log_emails(69)
        self.assertEqual(email_usage()['level'], 'ok')
        log_emails(1)  # 70
        self.assertEqual(email_usage()['level'], 'warning')
        log_emails(20)  # 90
        usage = email_usage()
        self.assertEqual(usage['level'], 'critical')
        self.assertIn('每日上限', usage['alerts'][0])
        self.assertIn('升級', usage['advice'])

    def test_ok_level_gives_no_advice(self):
        log_emails(5)
        usage = email_usage()
        self.assertEqual((usage['alerts'], usage['advice']), ([], ''))

    @override_settings(EMAIL_MONTHLY_LIMIT=100, EMAIL_DAILY_LIMIT=10000)
    def test_monthly_threshold(self):
        log_emails(70)
        usage = email_usage()
        self.assertEqual(usage['level'], 'warning')
        self.assertIn('每月上限', usage['alerts'][0])

    def test_limits_follow_settings_after_an_upgrade(self):
        log_emails(95)
        self.assertEqual(email_usage()['level'], 'critical')
        with override_settings(EMAIL_DAILY_LIMIT=1000):
            self.assertEqual(email_usage()['level'], 'ok')


class LoggingBackendTests(TestCase):
    @override_settings(EMAIL_BACKEND='stats.email_backend.LoggingSMTPBackend')
    def test_successful_send_is_logged_and_failure_is_not(self):
        from unittest.mock import patch
        from django.core.mail import EmailMessage
        from django.core.mail.backends.smtp import EmailBackend

        message = EmailMessage('hello', 'body', 'a@example.com', ['b@example.com', 'c@example.com'])
        with patch.object(EmailBackend, '_send', return_value=True):
            message.send()
        row = EmailLog.objects.get()
        self.assertEqual((row.recipient_count, row.subject), (2, 'hello'))

        EmailLog.objects.all().delete()
        with patch.object(EmailBackend, '_send', return_value=False):
            message.send()
        self.assertFalse(EmailLog.objects.exists())

    @override_settings(EMAIL_BACKEND='stats.email_backend.LoggingSMTPBackend')
    def test_log_failure_never_breaks_sending(self):
        from unittest.mock import patch
        from django.core.mail import EmailMessage
        from django.core.mail.backends.smtp import EmailBackend

        message = EmailMessage('hello', 'body', 'a@example.com', ['b@example.com'])
        with patch.object(EmailBackend, '_send', return_value=True), \
                patch('stats.models.EmailLog.objects') as manager:
            manager.create.side_effect = RuntimeError('db down')
            self.assertEqual(message.send(), 1)
