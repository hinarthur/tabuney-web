"""Separate, server-validated consent before redirecting to hosted Stripe Checkout."""
import hashlib
import uuid
from decimal import Decimal

from django import forms
from django.conf import settings
from django.core import signing
from django.core.mail import EmailMessage
from django.db import transaction
from django.shortcuts import render
from django.template import engines
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone, translation

from .models import CheckoutConsent

VERSION = '2026-10-31-v2'
SALT = 'commerce.checkout-consent.v1'
COPY = {
    'en': {
        'title': 'Confirm immediate access',
        'intro': 'Review these separate choices before continuing to Stripe. The total price, currency and billing interval will be shown there before you pay.',
        'digital': 'I expressly consent to immediate supply of the digital content before the end of the 14-day cancellation period, and acknowledge that I lose my 14-day cooling-off cancellation right for that digital content once its supply begins.',
        'service': 'I expressly request that any ongoing services start during the 14-day cancellation period. I understand that this does not immediately remove my cancellation right for those services, and that if I cancel after service has started I may have to pay a proportionate amount for the service already provided.',
        'terms': 'I agree to the Terms of Service for this purchase.',
        'button': 'Continue to Stripe',
        'note': 'Nothing here removes your rights if content or services are faulty, not supplied or not as described. Subscription renewal can still be cancelled. A confirmation copy will be emailed after checkout.',
        'error': 'Please actively confirm each separate choice to continue.',
        'expired': 'This confirmation has expired or the terms have changed. Please review the current text and confirm again.',
        'subscription': 'Tabuney subscription', 'edition': 'Edition unlock',
    },
    'zh': {
        'title': '確認即時取得內容及服務',
        'intro': '前往 Stripe 前，請分別確認以下選項。總價、貨幣及扣款週期會在 Stripe 付款前顯示。',
        'digital': '我明確同意在14天取消期結束前即時提供數位內容，並確認該數位內容開始提供後，我將失去就該數位內容行使14天冷靜期取消權的權利。',
        'service': '我明確要求在14天取消期內開始提供持續服務。我明白這不會立即取消我就該服務享有的取消權；如在服務開始後取消，我可能須就已提供的服務支付按比例計算的費用。',
        'terms': '我同意本次購買適用的使用條款。',
        'button': '繼續前往 Stripe',
        'note': '以上確認不影響內容或服務有瑕疵、未供應或不符描述時的法定補救權利，亦不妨礙取消訂閱續訂。完成結帳後，我們會寄出確認副本。',
        'error': '請主動勾選各項獨立確認，然後繼續。',
        'expired': '確認頁已過期或條款已更新，請重新閱讀並確認目前的內容。',
        'subscription': 'Tabuney 訂閱', 'edition': '版本內容解鎖',
    },
    'ja': {
        'title': 'デジタルコンテンツ・サービスの即時提供の確認',
        'intro': 'Stripeへ進む前に、以下の項目をそれぞれ確認してください。合計金額、通貨、請求間隔は、お支払い前にStripe上で表示されます。',
        'digital': '14日間の契約解除期間が終了する前にデジタルコンテンツが直ちに提供されることに明示的に同意します。また、当該デジタルコンテンツの提供が開始された時点で、そのデジタルコンテンツについての14日間のクーリングオフ（契約解除）の権利を失うことを理解しています。',
        'service': '継続的なサービスを14日間の契約解除期間中に開始するよう明示的に要求します。これにより当該サービスに関する解除権が直ちに失われるわけではないこと、またサービス開始後に解除した場合は、すでに提供されたサービスに応じた按分額を支払う必要が生じる場合があることを理解しています。',
        'terms': 'この購入について利用規約に同意します。',
        'button': 'Stripeへ進む',
        'note': 'ここでの確認は、コンテンツやサービスに欠陥がある場合、提供されなかった場合、または説明と異なる場合の法定の権利に影響しません。サブスクリプションの更新はいつでも解約できます。決済完了後、確認用の控えをメールでお送りします。',
        'error': '続行するには、各項目を個別に確認してください。',
        'expired': 'この確認の有効期限が切れたか、規約が更新されました。最新の内容をご確認のうえ、もう一度確認してください。',
        'subscription': 'Tabuney サブスクリプション', 'edition': 'エディションの解放',
    },
    'de': {
        'title': 'Sofortigen Zugang bestätigen',
        'intro': 'Bitte prüfen Sie diese getrennten Angaben, bevor Sie zu Stripe weitergehen. Gesamtpreis, Währung und Abrechnungsintervall werden dort vor der Zahlung angezeigt.',
        'digital': 'Ich stimme ausdrücklich zu, dass die Bereitstellung der digitalen Inhalte sofort, also vor Ablauf der 14-tägigen Widerrufsfrist, beginnt, und nehme zur Kenntnis, dass ich mein 14-tägiges Widerrufsrecht für diese digitalen Inhalte verliere, sobald deren Bereitstellung begonnen hat.',
        'service': 'Ich verlange ausdrücklich, dass fortlaufende Leistungen bereits während der 14-tägigen Widerrufsfrist beginnen. Mir ist bewusst, dass dies mein Widerrufsrecht für diese Leistungen nicht sofort aufhebt und dass ich, wenn ich nach Leistungsbeginn widerrufe, einen anteiligen Betrag für die bereits erbrachte Leistung zahlen muss.',
        'terms': 'Ich stimme den Nutzungsbedingungen für diesen Kauf zu.',
        'button': 'Weiter zu Stripe',
        'note': 'Hierdurch werden Ihre gesetzlichen Rechte bei mangelhaften, nicht gelieferten oder nicht der Beschreibung entsprechenden Inhalten oder Leistungen nicht berührt. Die Verlängerung eines Abonnements können Sie weiterhin kündigen. Nach dem Bezahlvorgang erhalten Sie eine Bestätigungskopie per E-Mail.',
        'error': 'Bitte bestätigen Sie jede Angabe einzeln, um fortzufahren.',
        'expired': 'Diese Bestätigung ist abgelaufen oder die Bedingungen haben sich geändert. Bitte lesen Sie den aktuellen Text und bestätigen Sie erneut.',
        'subscription': 'Tabuney-Abonnement', 'edition': 'Edition freischalten',
    },
    'fr': {
        'title': 'Confirmer l’accès immédiat',
        'intro': 'Veuillez vérifier ces choix distincts avant de continuer vers Stripe. Le prix total, la devise et la périodicité de facturation y seront affichés avant le paiement.',
        'digital': 'Je consens expressément à la fourniture immédiate du contenu numérique avant la fin du délai de rétractation de 14 jours, et je reconnais que je perds mon droit de rétractation de 14 jours pour ce contenu numérique dès que sa fourniture a commencé.',
        'service': 'Je demande expressément que les services continus commencent pendant le délai de rétractation de 14 jours. Je comprends que cela ne supprime pas immédiatement mon droit de rétractation pour ces services et que, si je me rétracte après le début du service, je pourrai devoir payer un montant proportionnel au service déjà fourni.',
        'terms': 'J’accepte les Conditions d’utilisation pour cet achat.',
        'button': 'Continuer vers Stripe',
        'note': 'Rien ici ne supprime vos droits si le contenu ou les services sont défectueux, non fournis ou non conformes à la description. Le renouvellement de l’abonnement reste résiliable. Une copie de confirmation vous sera envoyée par e-mail après le paiement.',
        'error': 'Veuillez confirmer activement chaque choix distinct pour continuer.',
        'expired': 'Cette confirmation a expiré ou les conditions ont changé. Veuillez relire le texte actuel et confirmer à nouveau.',
        'subscription': 'Abonnement Tabuney', 'edition': 'Déblocage d’édition',
    },
    'es': {
        'title': 'Confirmar acceso inmediato',
        'intro': 'Revisa estas opciones por separado antes de continuar a Stripe. El precio total, la moneda y el intervalo de facturación se mostrarán allí antes de pagar.',
        'digital': 'Doy mi consentimiento expreso para el suministro inmediato del contenido digital antes de que termine el plazo de desistimiento de 14 días, y reconozco que pierdo mi derecho de desistimiento de 14 días respecto a ese contenido digital una vez que comience su suministro.',
        'service': 'Solicito expresamente que los servicios continuados comiencen durante el plazo de desistimiento de 14 días. Entiendo que esto no elimina de inmediato mi derecho de desistimiento respecto a esos servicios y que, si desisto una vez iniciado el servicio, es posible que deba pagar un importe proporcional al servicio ya prestado.',
        'terms': 'Acepto los Términos de uso para esta compra.',
        'button': 'Continuar a Stripe',
        'note': 'Nada de esto afecta a tus derechos si el contenido o los servicios son defectuosos, no se suministran o no se corresponden con la descripción. La renovación de la suscripción se puede seguir cancelando. Recibirás una copia de confirmación por correo electrónico tras el pago.',
        'error': 'Confirma activamente cada opción por separado para continuar.',
        'expired': 'Esta confirmación ha caducado o las condiciones han cambiado. Revisa el texto actual y confirma de nuevo.',
        'subscription': 'Suscripción a Tabuney', 'edition': 'Desbloqueo de edición',
    },
}


# Wording of the confirmation email, per consent-page language. Kept apart from COPY so the page
# and the email can be edited independently; load_copy() merges both into one dict.
EMAIL_COPY = {
    'en': {
        'email_subject': 'Tabuney — purchase and consent confirmation',
        'email_purchase': 'Purchase:',
        'email_reference': 'Stripe reference:',
        'email_total': 'Checkout total:',
        'email_confirmed_at': 'Confirmed at (UTC):',
        'email_version': 'Consent version:',
        'email_confirmed': 'Confirmed separately:',
        'email_legal': 'Your cooling-off cancellation right for digital content is lost only once its supply begins. This does not remove statutory remedies for faulty or missing content, or immediately remove cancellation rights for ongoing services. You can turn off subscription renewal on the membership page. Contact info@tabuney.com about cancellation or refunds.',
        'email_attached': 'Attached are the Terms of Service and Privacy Policy shown when you confirmed.',
    },
    'zh': {
        'email_subject': 'Tabuney — 購買及同意確認',
        'email_purchase': '購買項目：',
        'email_reference': 'Stripe 參考編號：',
        'email_total': '結帳總額：',
        'email_confirmed_at': '確認時間（UTC）：',
        'email_version': '同意條款版本：',
        'email_confirmed': '已分別確認：',
        'email_legal': '數位內容的14天冷靜期取消權，只會在內容開始提供後才喪失。這不影響您就有瑕疵或未供應的內容享有的法定補救權利，亦不會立即取消您就持續服務享有的取消權。您可在會員頁面關閉訂閱續訂。如有取消或退款問題，請聯絡 info@tabuney.com。',
        'email_attached': '附件為您確認時所顯示的使用條款及隱私政策。',
    },
    'ja': {
        'email_subject': 'Tabuney — ご購入および同意内容の確認',
        'email_purchase': 'ご購入内容：',
        'email_reference': 'Stripe 参照番号：',
        'email_total': 'お支払い合計：',
        'email_confirmed_at': '確認日時（UTC）：',
        'email_version': '同意文言のバージョン：',
        'email_confirmed': '個別に確認された事項：',
        'email_legal': 'デジタルコンテンツに関する14日間のクーリングオフの権利は、そのコンテンツの提供が開始された時点でのみ失われます。これにより、欠陥のある、または提供されなかったコンテンツに対する法定の救済措置が失われることはなく、継続的なサービスに関する解除権が直ちに失われることもありません。サブスクリプションの自動更新は、会員ページで停止できます。解約や返金については info@tabuney.com までご連絡ください。',
        'email_attached': 'ご確認時に表示された利用規約とプライバシーポリシーを添付しています。',
    },
    'de': {
        'email_subject': 'Tabuney — Bestätigung von Kauf und Einwilligung',
        'email_purchase': 'Kauf:',
        'email_reference': 'Stripe-Referenz:',
        'email_total': 'Gesamtbetrag:',
        'email_confirmed_at': 'Bestätigt am (UTC):',
        'email_version': 'Version der Einwilligung:',
        'email_confirmed': 'Einzeln bestätigt:',
        'email_legal': 'Ihr Widerrufsrecht für digitale Inhalte erlischt erst, sobald deren Bereitstellung begonnen hat. Gesetzliche Rechte bei mangelhaften oder nicht bereitgestellten Inhalten bleiben unberührt, und das Widerrufsrecht für fortlaufende Leistungen erlischt dadurch nicht sofort. Die Verlängerung Ihres Abonnements können Sie auf der Mitgliedschaftsseite deaktivieren. Fragen zu Kündigung oder Erstattung richten Sie bitte an info@tabuney.com.',
        'email_attached': 'Anbei finden Sie die Nutzungsbedingungen und die Datenschutzrichtlinie, wie sie Ihnen bei Ihrer Bestätigung angezeigt wurden.',
    },
    'fr': {
        'email_subject': 'Tabuney — confirmation d’achat et de consentement',
        'email_purchase': 'Achat :',
        'email_reference': 'Référence Stripe :',
        'email_total': 'Total du paiement :',
        'email_confirmed_at': 'Confirmé le (UTC) :',
        'email_version': 'Version du consentement :',
        'email_confirmed': 'Confirmé séparément :',
        'email_legal': 'Votre droit de rétractation pour le contenu numérique n’est perdu qu’une fois sa fourniture commencée. Cela ne supprime pas vos droits légaux en cas de contenu défectueux ou non fourni, ni, immédiatement, votre droit de rétractation pour les services continus. Vous pouvez désactiver le renouvellement de l’abonnement depuis la page d’adhésion. Pour toute question sur la rétractation ou le remboursement, écrivez à info@tabuney.com.',
        'email_attached': 'Vous trouverez en pièces jointes les Conditions d’utilisation et la Politique de confidentialité affichées lors de votre confirmation.',
    },
    'es': {
        'email_subject': 'Tabuney — confirmación de compra y consentimiento',
        'email_purchase': 'Compra:',
        'email_reference': 'Referencia de Stripe:',
        'email_total': 'Total del pago:',
        'email_confirmed_at': 'Confirmado el (UTC):',
        'email_version': 'Versión del consentimiento:',
        'email_confirmed': 'Confirmado por separado:',
        'email_legal': 'Tu derecho de desistimiento respecto al contenido digital solo se pierde una vez que comienza su suministro. Esto no elimina tus derechos legales si el contenido es defectuoso o no se suministra, ni elimina de inmediato tu derecho de desistimiento respecto a los servicios continuados. Puedes desactivar la renovación de la suscripción en la página de membresía. Para consultas sobre cancelaciones o reembolsos, escribe a info@tabuney.com.',
        'email_attached': 'Adjuntamos los Términos de uso y la Política de privacidad que se mostraron cuando confirmaste.',
    },
}


# Each product asks only for the waiver that applies to it. A one-off edition unlock is digital
# content (no ongoing service); the membership is an ongoing service. Asking for both would make
# an edition buyer confirm a service they are not buying, and vice versa.
REQUIRED_CHOICES = {
    'subscription': ('service_start_consent',),
    'edition_unlock': ('digital_content_consent',),
}
KEY_PREFIX = 'checkout.consent.'
# Labels shared with the site footer / buttons, so the link text always matches the policy pages.
SHARED_KEYS = {'back': 'btn.back', 'terms_label': 'terms_of_use', 'privacy_label': 'privacy_policy'}
SHARED_FALLBACK = {'back': 'Back', 'terms_label': 'Terms of Service', 'privacy_label': 'Privacy Policy'}
LEGAL_KEYS = ('digital', 'service', 'terms')


class ConsentForm(forms.Form):
    consent_token = forms.CharField(widget=forms.HiddenInput)
    digital_content_consent = forms.BooleanField(required=False)
    service_start_consent = forms.BooleanField(required=False)
    accept_terms = forms.BooleanField(required=True)

    def __init__(self, *args, kind, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('digital_content_consent', 'service_start_consent'):
            self.fields[name].required = name in REQUIRED_CHOICES[kind]


def _table_copy(lang):
    from translation.models import Translation
    return {
        key[len(KEY_PREFIX):]: value for key, value in Translation.objects.filter(
            tribe__language=lang, key__startswith=KEY_PREFIX).values_list('key', 'value') if value
    }


def _shared_copy(lang):
    from translation.models import Translation
    by_key = dict(Translation.objects.filter(
        tribe__language=lang, key__in=SHARED_KEYS.values()).values_list('key', 'value'))
    return {name: by_key[key] for name, key in SHARED_KEYS.items() if by_key.get(key)}


def load_copy(lang):
    """(wording_lang, copy) for the page language.

    Wording lives in the translation table (keys checkout.consent.*) so it is editable in the
    admin; COPY is the built-in fallback. A language only gets its own legal wording once it is in
    COPY or has all of LEGAL_KEYS in the table; otherwise the buyer sees English consistently
    rather than a half-translated waiver.
    """
    rows = _table_copy(lang)
    if lang not in COPY and not all(key in rows for key in LEGAL_KEYS):
        return 'en', {**COPY['en'], **EMAIL_COPY['en'], **SHARED_FALLBACK, **_shared_copy('en'), **_table_copy('en')}
    return lang, {**COPY['en'], **EMAIL_COPY['en'], **SHARED_FALLBACK, **COPY.get(lang, {}),
                  **EMAIL_COPY.get(lang, {}), **_shared_copy(lang), **rows}


def policy_copy(name):
    """Freeze the visible policy, without navigation or executable template markup."""
    source = get_template(name).template.source
    fragment = source[source.index('<div class="policy">'):source.rindex('</div>') + 6]
    rendered = engines['django'].from_string(fragment).render({})
    return '<!doctype html><html lang="en"><meta charset="utf-8"><body>' + rendered + '</body></html>'


def prepare_checkout(request, kind, lang, product_id='', product_label='', back_url='/'):
    """Return (response, None) until all choices and the bound signed token validate."""
    wording_lang, copy = load_copy(lang)
    # /commerce/ is unprefixed, so request.lang comes from a stale session; base.html renders from it.
    request.lang = lang
    required = REQUIRED_CHOICES[kind]
    with translation.override(lang):
        terms_html = policy_copy('terms.html')
        privacy_html = policy_copy('privacy.html')
        terms_url = request.build_absolute_uri(reverse('terms'))
        privacy_url = request.build_absolute_uri(reverse('privacy'))
        # Absolute links remain usable in the emailed attachments, in the selected language.
        terms_html = terms_html.replace('href="' + reverse('privacy') + '"', 'href="' + privacy_url + '"')
    binding = {
        'user': str(request.user.pk), 'kind': kind, 'product': str(product_id),
        'lang': lang, 'wording_lang': wording_lang, 'version': VERSION,
        'terms': hashlib.sha256(terms_html.encode()).hexdigest(),
        'privacy': hashlib.sha256(privacy_html.encode()).hexdigest(),
        # Wording edited in the admin between render and submit must not be recorded as accepted.
        'copy': hashlib.sha256('\n'.join(copy[key] for key in LEGAL_KEYS).encode()).hexdigest(),
    }
    form = ConsentForm(request.POST if request.POST.get('consent_token') else None, kind=kind)
    error = ''
    if form.is_bound and form.is_valid():
        try:
            payload = signing.loads(form.cleaned_data['consent_token'], salt=SALT, max_age=3600)
            if any(payload.get(key) != value for key, value in binding.items()):
                raise signing.BadSignature('Checkout context changed')
            # Every required BooleanField must have passed server validation. Never trust hidden flags.
            record, _ = CheckoutConsent.objects.get_or_create(
                request_key=hashlib.sha256(form.cleaned_data['consent_token'].encode()).hexdigest(),
                defaults={
                    'user_id': request.user.pk, 'kind': kind, 'product_id': str(product_id),
                    'product_label': product_label or copy['subscription'], 'language': wording_lang,
                    'version': VERSION,
                    'digital_text': copy['digital'] if 'digital_content_consent' in required else '',
                    'service_text': copy['service'] if 'service_start_consent' in required else '',
                    'terms_text': copy['terms'], 'terms_html': terms_html, 'privacy_html': privacy_html,
                    'confirmation_email': request.user.email,
                },
            )
            return None, record
        except signing.BadSignature:
            error = copy['expired']
    elif form.is_bound:
        error = copy['error']
    payload = dict(binding, nonce=str(uuid.uuid4()))
    token = signing.dumps(payload, salt=SALT, compress=True)
    with translation.override(lang):
        response = render(request, 'commerce/checkout_consent.html', {
            'copy': copy, 'consent_token': token, 'lang': lang, 'wording_lang': wording_lang,
            'product_id': product_id, 'product_label': product_label or copy['subscription'],
            'back_url': back_url, 'terms_url': terms_url, 'privacy_url': privacy_url,
            'error': error,
            'ask_digital': 'digital_content_consent' in required,
            'ask_service': 'service_start_consent' in required,
        }, status=400 if error else 200)
    return response, None


def consent_metadata(record):
    return {
        'checkout_consent_id': str(record.pk),
        'checkout_consent_version': record.version,
        'checkout_consent_at': record.confirmed_at.isoformat(),
    }


def confirm_paid_checkout(session):
    """Email the exact consent/policy copies before new-consent purchases are provisioned.

    Old sessions have no consent identifier: honour those purchases without inventing a waiver.
    SMTP failure raises so a signed Stripe webhook can retry; delivery is not silently dropped.
    """
    consent_id = (session.get('metadata') or {}).get('checkout_consent_id')
    if not consent_id:
        return
    if session.get('payment_status') not in ('paid', 'no_payment_required'):
        raise ValueError('Checkout payment is not complete')
    with transaction.atomic():
        record = CheckoutConsent.objects.select_for_update().get(pk=consent_id)
        if (record.stripe_session_id != session.get('id')
                or str(record.user_id) != str(session.get('client_reference_id'))
                or (record.kind == 'subscription' and session.get('mode') != 'subscription')
                or (record.kind == 'edition_unlock' and
                    (session.get('mode') != 'payment'
                     or (session.get('metadata') or {}).get('kind') != 'edition_unlock'
                     or record.product_id != (session.get('metadata') or {}).get('edition_id')))):
            raise ValueError('Checkout consent does not match payment')
        if record.confirmation_sent_at:
            return
        if not record.confirmation_email:
            raise ValueError('No confirmation email recorded')
        currency = (session.get('currency') or '').upper()
        zero_decimal = {'BIF', 'CLP', 'DJF', 'GNF', 'JPY', 'KMF', 'KRW', 'MGA', 'PYG', 'RWF', 'UGX', 'VND', 'VUV', 'XAF', 'XOF', 'XPF'}
        amount = Decimal(session.get('amount_total') or 0) / (1 if currency in zero_decimal else 100)
        # The consent texts were stored in the buyer's language; the surrounding wording follows it.
        _, copy = load_copy(record.language)
        body = (
            f"{copy['email_subject']}\n\n"
            f"{copy['email_purchase']} {record.product_label}\n"
            f"{copy['email_reference']} {record.stripe_session_id}\n"
            f"{copy['email_total']} {amount} {currency}\n"
            f"{copy['email_confirmed_at']} {record.confirmed_at.isoformat()}\n"
            f"{copy['email_version']} {record.version}\n\n"
            f"{copy['email_confirmed']}\n\n"
            + ''.join(f'{text}\n\n' for text in (record.digital_text, record.service_text) if text)
            + f'{record.terms_text}\n\n'
            + f"{copy['email_legal']}\n\n"
            + f"{copy['email_attached']}\n"
        )
        email = EmailMessage(copy['email_subject'], body,
                             settings.DEFAULT_FROM_EMAIL, [record.confirmation_email])
        email.attach('Tabuney-Terms.html', record.terms_html, 'text/html')
        email.attach('Tabuney-Privacy.html', record.privacy_html, 'text/html')
        if email.send(fail_silently=False) != 1:
            raise RuntimeError('Confirmation email was not accepted by the mail backend')
        record.confirmation_sent_at = timezone.now()
        record.save(update_fields=['confirmation_sent_at'])
