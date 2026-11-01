from types import SimpleNamespace, ModuleType
from unittest.mock import patch
import sys
import uuid

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings

from . import views
from .checkout_consent import COPY, EMAIL_COPY, prepare_checkout, confirm_paid_checkout
from .models import CheckoutConsent


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    STRIPE_FLOWCHART_SINGLE_EDITION_PRICE_ID='price_edition_test',
    STRIPE_RECURRING_US699_PRICE_ID='price_subscription_test',
)
class CheckoutConsentTests(TestCase):
    def setUp(self):
        # Bypass unrelated project profile signals; the request still belongs to a real auth user.
        get_user_model().objects.bulk_create([
            get_user_model()(username='checkout-test', email='buyer@example.com')
        ])
        self.user_id = get_user_model().objects.get(username='checkout-test').pk
        self.user = SimpleNamespace(
            pk=self.user_id, id=self.user_id, email='buyer@example.com', is_authenticated=True,
            member=SimpleNamespace(stripe_customer_id=None, has_unlocked=lambda edition_id: False),
        )
        self.factory = RequestFactory()

    def request(self, data=None):
        request = self.factory.post('/commerce/create-checkout-session/', data or {'lang': 'en'})
        request.user = self.user
        return request

    def payload(self, kind='subscription', product=''):
        request = self.request()
        with patch('commerce.checkout_consent.render') as render:
            prepare_checkout(request, kind, 'en', product_id=product)
            token = render.call_args.args[2]['consent_token']
        return dict(lang='en', consent_token=token, digital_content_consent='yes',
                    service_start_consent='yes', accept_terms='yes', edition_id=product)

    def paid(self, record, **extra):
        record.stripe_session_id = 'cs_test_consent'
        record.save(update_fields=['stripe_session_id'])
        session = dict(id=record.stripe_session_id, client_reference_id=str(self.user_id),
                       payment_status='paid', mode='subscription', amount_total=699, currency='usd',
                       metadata={'checkout_consent_id': str(record.pk)})
        session.update(extra)
        return session

    def record(self):
        _, record = prepare_checkout(self.request(self.payload()), 'subscription', 'en')
        return record

    @patch('commerce.views.stripe.checkout.Session.create')
    def test_initial_subscription_request_shows_unchecked_separate_choices(self, create):
        response = views.create_checkout_session(self.request())
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # Membership is an ongoing service: only the service waiver applies.
        for field in ('service_start_consent', 'accept_terms'):
            self.assertIn(f'name="{field}"', html)
        self.assertNotIn('name="digital_content_consent"', html)
        self.assertNotIn(' checked', html)
        create.assert_not_called()
        self.assertFalse(CheckoutConsent.objects.exists())

    @patch('commerce.views.stripe.checkout.Session.create')
    def test_missing_each_checkbox_is_rejected_server_side(self, create):
        payload = self.payload()
        for field in ('service_start_consent', 'accept_terms'):
            data = dict(payload); data.pop(field)
            self.assertEqual(views.create_checkout_session(self.request(data)).status_code, 400)
        create.assert_not_called()
        self.assertFalse(CheckoutConsent.objects.exists())

    def test_each_product_asks_and_records_only_its_own_waiver(self):
        response, _ = prepare_checkout(self.request(), 'edition_unlock', 'en', product_id='e1')
        html = response.content.decode()
        self.assertIn('name="digital_content_consent"', html)
        self.assertNotIn('name="service_start_consent"', html)
        data = self.payload('edition_unlock', 'e1'); data.pop('digital_content_consent')
        response, record = prepare_checkout(self.request(data), 'edition_unlock', 'en', product_id='e1')
        self.assertEqual(response.status_code, 400)
        data = self.payload('edition_unlock', 'e1'); data.pop('service_start_consent')
        response, record = prepare_checkout(self.request(data), 'edition_unlock', 'en', product_id='e1')
        self.assertIsNone(response)
        self.assertEqual(record.service_text, '')
        self.assertEqual(record.digital_text, COPY['en']['digital'])

    def test_page_renders_in_requested_language_not_stale_session_language(self):
        request = self.request()
        request.lang = 'ja'  # what LanguageMiddleware yields under /commerce/ from an old session
        response, _ = prepare_checkout(request, 'subscription', 'zh')
        self.assertEqual(request.lang, 'zh')
        self.assertIn('lang="zh"', response.content.decode())
        self.assertIn(COPY['zh']['title'], response.content.decode())

    def test_admin_edited_wording_between_render_and_submit_is_rejected(self):
        data = self.payload()
        changed = {**COPY['en'], 'service': 'changed wording'}
        with patch('commerce.checkout_consent.load_copy', return_value=('en', changed)):
            response, _ = prepare_checkout(self.request(data), 'subscription', 'en')
        self.assertEqual(response.status_code, 400)

    @patch('commerce.views.stripe.checkout.Session.create')
    def test_forged_or_expired_token_does_not_create_checkout(self, create):
        data = self.payload(); data['consent_token'] += 'tampered'
        self.assertEqual(views.create_checkout_session(self.request(data)).status_code, 400)
        data = self.payload()
        with patch('django.core.signing.time.time', return_value=9999999999):
            self.assertEqual(views.create_checkout_session(self.request(data)).status_code, 400)
        create.assert_not_called()

    @patch('commerce.views.stripe.checkout.Session.create')
    def test_token_is_bound_to_buyer_product_and_current_policy(self, create):
        data = self.payload()
        self.user.pk = 999
        response, _ = prepare_checkout(self.request(data), 'subscription', 'en')
        self.assertEqual(response.status_code, 400)
        self.user.pk = self.user_id
        response, _ = prepare_checkout(self.request(data), 'edition_unlock', 'en', product_id='another')
        self.assertEqual(response.status_code, 400)
        with patch('commerce.checkout_consent.policy_copy', return_value='<p>Changed policy</p>'):
            response, _ = prepare_checkout(self.request(data), 'subscription', 'en')
        self.assertEqual(response.status_code, 400)
        create.assert_not_called()

    @patch('commerce.views.stripe.checkout.Session.create')
    def test_valid_subscription_attaches_proof_and_reuses_idempotency_key(self, create):
        create.return_value = SimpleNamespace(id='cs_test_1', url='https://checkout.stripe.com/test')
        payload = self.payload()
        for _ in range(2):
            self.assertEqual(views.create_checkout_session(self.request(payload)).status_code, 303)
        self.assertEqual(CheckoutConsent.objects.count(), 1)
        record = CheckoutConsent.objects.get()
        self.assertEqual(record.stripe_session_id, 'cs_test_1')
        for call in create.call_args_list:
            self.assertEqual(call.kwargs['metadata']['checkout_consent_id'], str(record.pk))
            self.assertEqual(call.kwargs['idempotency_key'], f'checkout-consent-{record.pk}')

    @patch('commerce.views.stripe.checkout.Session.create')
    def test_edition_checkout_also_requires_consent_and_preserves_metadata(self, create):
        edition_id = str(uuid.uuid4())
        edition = SimpleNamespace(id=edition_id, get_absolute_url=lambda: '/games/test/')
        game_models = ModuleType('game.models')
        game_models.Edition = SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: SimpleNamespace(first=lambda: edition)))
        selectors = ModuleType('game.selectors')
        selectors.editions_with_published_flowchart = lambda ids: set(ids)
        with patch.dict(sys.modules, {'game.models': game_models, 'game.selectors': selectors}):
            response = views.create_edition_unlock_session(self.request({'edition_id': edition_id, 'lang': 'en'}))
            self.assertEqual(response.status_code, 200)
            create.assert_not_called()
            create.return_value = SimpleNamespace(id='cs_edition', url='https://checkout.stripe.com/test')
            response = views.create_edition_unlock_session(self.request(self.payload('edition_unlock', edition_id)))
            self.assertEqual(response.status_code, 303)
        metadata = create.call_args.kwargs['metadata']
        self.assertEqual(metadata['edition_id'], edition_id)
        self.assertEqual(metadata['kind'], 'edition_unlock')
        self.assertIn('checkout_consent_id', metadata)
        self.assertEqual(metadata, create.call_args.kwargs['payment_intent_data']['metadata'])

    def test_confirmation_sends_exact_wording_and_frozen_policy_copies_once(self):
        record = self.record(); session = self.paid(record)
        confirm_paid_checkout(session)
        confirm_paid_checkout(session)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(record.digital_text, mail.outbox[0].body)
        self.assertIn('6.99 USD', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['buyer@example.com'])
        self.assertEqual(mail.outbox[0].attachments[0][1], record.terms_html)
        self.assertEqual(mail.outbox[0].attachments[1][1], record.privacy_html)
        record.refresh_from_db(); self.assertIsNotNone(record.confirmation_sent_at)

    def test_confirmation_email_follows_the_buyers_language(self):
        record = self.record()
        record.language = 'ja'
        record.save(update_fields=['language'])
        confirm_paid_checkout(self.paid(record))
        message = mail.outbox[0]
        self.assertEqual(message.subject, EMAIL_COPY['ja']['email_subject'])
        self.assertIn(EMAIL_COPY['ja']['email_legal'], message.body)
        self.assertNotIn('Stripe reference', message.body)

    def test_every_language_has_the_same_email_keys(self):
        for lang, strings in EMAIL_COPY.items():
            self.assertEqual(set(strings), set(EMAIL_COPY['en']), lang)

    def test_no_waiver_is_invented_for_legacy_checkout(self):
        confirm_paid_checkout({'metadata': {}})
        self.assertEqual(len(mail.outbox), 0)

    def test_unpaid_or_wrong_buyer_or_session_cannot_use_consent(self):
        record = self.record(); session = self.paid(record)
        for bad in ({'payment_status': 'unpaid'}, {'client_reference_id': '999'}, {'id': 'cs_wrong'}, {'mode': 'payment'}):
            with self.assertRaises(ValueError):
                confirm_paid_checkout(dict(session, **bad))
        self.assertEqual(len(mail.outbox), 0)

    def test_failed_email_leaves_record_retryable(self):
        record = self.record(); session = self.paid(record)
        with patch('commerce.checkout_consent.EmailMessage.send', side_effect=OSError('SMTP unavailable')):
            with self.assertRaises(OSError):
                confirm_paid_checkout(session)
        record.refresh_from_db(); self.assertIsNone(record.confirmation_sent_at)
        confirm_paid_checkout(session)
        self.assertEqual(len(mail.outbox), 1)

    def test_webhook_retries_email_failure_before_any_access_is_granted(self):
        session = self.paid(self.record())
        event = {'id': 'evt_test', 'type': 'checkout.session.completed', 'data': {'object': session}}
        with patch('commerce.views.stripe.Webhook.construct_event', return_value=event), \
                patch('commerce.checkout_consent.EmailMessage.send', side_effect=OSError('SMTP unavailable')), \
                patch('commerce.views.Member.objects.get') as get_member, \
                self.assertLogs('commerce.views', level='ERROR'):
            response = views.stripe_webhook(self.factory.post('/commerce/webhook/', b'{}', content_type='application/json'))
        self.assertEqual(response.status_code, 500)
        get_member.assert_not_called()

    def test_unpaid_completed_event_waits_for_async_payment(self):
        event = {'id': 'evt_test', 'type': 'checkout.session.completed',
                 'data': {'object': {'payment_status': 'unpaid'}}}
        with patch('commerce.views.stripe.Webhook.construct_event', return_value=event), \
                patch('commerce.views.confirm_paid_checkout') as confirm, \
                patch('commerce.views.Member.objects.get') as get_member:
            response = views.stripe_webhook(self.factory.post('/commerce/webhook/', b'{}', content_type='application/json'))
        self.assertEqual(response.status_code, 200)
        confirm.assert_not_called(); get_member.assert_not_called()

    def test_async_paid_event_confirms_before_fulfilment(self):
        session = self.paid(self.record(), mode='payment')
        record = CheckoutConsent.objects.get()
        record.kind = 'edition_unlock'; record.product_id = 'edition-test'; record.save()
        session['metadata'].update(kind='edition_unlock', edition_id='edition-test')
        event = {'id': 'evt_async', 'type': 'checkout.session.async_payment_succeeded', 'data': {'object': session}}
        with patch('commerce.views.stripe.Webhook.construct_event', return_value=event), \
                patch('commerce.views.Member.objects.get', return_value=SimpleNamespace(stripe_customer_id=None, save=lambda: None)), \
                patch('commerce.views._ensure_transaction', return_value=object()), \
                patch('commerce.views._grant_edition_unlock') as grant:
            response = views.stripe_webhook(self.factory.post('/commerce/webhook/', b'{}', content_type='application/json'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        grant.assert_called_once()

    def test_success_page_cannot_bypass_confirmation_email(self):
        record = self.record(); record.kind='edition_unlock'; record.product_id='edition-test'; record.save()
        session = self.paid(record, mode='payment')
        session['metadata'].update(kind='edition_unlock', edition_id='edition-test')
        member = SimpleNamespace(pk=self.user_id, has_unlocked=lambda edition: False)
        with patch('commerce.views.stripe.checkout.Session.retrieve', return_value=session), \
                patch('commerce.checkout_consent.EmailMessage.send', side_effect=OSError('SMTP unavailable')), \
                patch('commerce.views._grant_edition_unlock') as grant, \
                self.assertLogs('commerce.views', level='ERROR'):
            self.assertFalse(views.fulfil_edition_unlock_from_session(member, SimpleNamespace(id='edition-test'), session['id']))
        grant.assert_not_called()

    def test_wrong_edition_cannot_use_another_purchase_consent(self):
        record = self.record(); record.kind='edition_unlock'; record.product_id='edition-test'; record.save()
        session = self.paid(record, mode='payment')
        session['metadata'].update(kind='edition_unlock', edition_id='other-edition')
        with self.assertRaises(ValueError):
            confirm_paid_checkout(session)
        self.assertEqual(len(mail.outbox), 0)

    def test_zh_wording_is_frozen_and_unsupported_language_uses_explicit_english(self):
        for lang, wording_lang in (('zh', 'zh'), ('ja', 'ja'), ('de', 'de'), ('fr', 'fr'), ('es', 'es'), ('ko', 'en')):
            with patch('commerce.checkout_consent.render') as render:
                prepare_checkout(self.request(), 'subscription', lang)
                context = render.call_args.args[2]
            self.assertEqual(context['wording_lang'], wording_lang)
            self.assertEqual(context['copy']['digital'], COPY[wording_lang]['digital'])


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   CONTACT_NOTIFY_EMAIL='owner@example.com')
class BillingSafetyTests(CheckoutConsentTests):
    """重複訂閱、開通失敗重試與通知、取消／恢復的錯誤顯示、續費失敗。"""

    def webhook(self, event):
        with patch('commerce.views.stripe.Webhook.construct_event', return_value=event):
            return views.stripe_webhook(self.factory.post('/commerce/webhook/', b'{}', content_type='application/json'))

    def test_existing_live_subscription_blocks_new_checkout(self):
        self.user.member.subscription = SimpleNamespace(status='active')
        with patch('commerce.views.stripe.checkout.Session.create') as create, \
                patch('commerce.views.messages'):
            response = views.create_checkout_session(self.request())
        self.assertEqual(response.status_code, 302)
        create.assert_not_called()

    def test_stripe_side_live_subscription_blocks_even_without_local_record(self):
        self.user.member.stripe_customer_id = 'cus_1'
        listing = SimpleNamespace(auto_paging_iter=lambda: iter([{'status': 'past_due'}]))
        with patch('commerce.views.stripe.Subscription.list', return_value=listing), \
                patch('commerce.views.stripe.checkout.Session.create') as create, \
                patch('commerce.views.messages'):
            response = views.create_checkout_session(self.request())
        self.assertEqual(response.status_code, 302)
        create.assert_not_called()

    def test_provisioning_failure_returns_500_and_alerts_owner(self):
        session = self.paid(self.record())
        event = {'id': 'evt_x', 'type': 'checkout.session.completed', 'data': {'object': session}}
        with patch('commerce.views.Member.objects.get', side_effect=RuntimeError('db down')), \
                self.assertLogs('commerce.views', level='ERROR'):
            response = self.webhook(event)
        self.assertEqual(response.status_code, 500)
        self.assertTrue(any('owner@example.com' in m.to for m in mail.outbox))

    def test_unlock_failure_propagates_so_stripe_retries(self):
        session = {'id': 'cs_1', 'metadata': {'kind': 'edition_unlock', 'edition_id': 'e1'}}
        member = SimpleNamespace(pk=1)
        with patch('member.models.EditionUnlock.objects.get_or_create', side_effect=RuntimeError('boom')), \
                self.assertLogs('commerce.views', level='ERROR'):
            with self.assertRaises(RuntimeError):
                views._grant_edition_unlock(session, member, object())
        self.assertEqual(len(mail.outbox), 1)

    def test_cancel_failure_is_reported_and_state_unchanged(self):
        sub = SimpleNamespace(stripe_subscription_id='sub_1', cancel_at_period_end=False, save=lambda **k: None)
        self.user.member.subscription = sub
        request = self.request()
        with patch('commerce.views.stripe.Subscription.modify', side_effect=RuntimeError('api')), \
                patch('commerce.views.messages') as msgs, \
                patch('commerce.views.redirect'), \
                self.assertLogs('commerce.views', level='ERROR'):
            views.cancel_subscription(request)
        msgs.error.assert_called_once()
        msgs.success.assert_not_called()
        self.assertFalse(sub.cancel_at_period_end)

    def test_cancel_success_updates_state_and_reports(self):
        sub = SimpleNamespace(stripe_subscription_id='sub_1', cancel_at_period_end=False, save=lambda **k: None)
        self.user.member.subscription = sub
        with patch('commerce.views.stripe.Subscription.modify', return_value={'cancel_at_period_end': True}), \
                patch('commerce.views.messages') as msgs, patch('commerce.views.redirect'):
            views.cancel_subscription(self.request())
        msgs.success.assert_called_once()
        self.assertTrue(sub.cancel_at_period_end)
