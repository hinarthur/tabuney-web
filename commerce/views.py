import stripe
import datetime
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import Transaction, Subscription
from .checkout_consent import prepare_checkout, consent_metadata, confirm_paid_checkout
from member.models import Member, Tier
from member.beta import beta_closed

stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)

# 這些狀態代表 Stripe 上還有一份會（繼續）扣款的訂閱，不可再開第二份。
LIVE_SUBSCRIPTION_STATUSES = ('active', 'trialing', 'past_due', 'unpaid')


def _alert_admin(subject, body):
    """通知站長處理。寄信失敗也不能讓呼叫端出錯（log 已經留了）。"""
    try:
        send_mail(f'[Tabuney billing] {subject}', body, settings.DEFAULT_FROM_EMAIL,
                  [settings.CONTACT_NOTIFY_EMAIL], fail_silently=False)
    except Exception:
        logger.exception('Admin alert email failed: %s | %s', subject, body)


def _text(request, key, default, lang=None):
    """翻譯表有就用，沒有就退回內建英文（_unlock_msg 查不到會回 key 本身）。"""
    value = _unlock_msg(request, key, lang)
    return default if value == key else value


def _has_live_subscription(member):
    """本地紀錄或 Stripe 上已有有效訂閱。本地漏記（如 webhook 失敗）時以 Stripe 為準。"""
    sub = getattr(member, 'subscription', None)
    if sub and sub.status in LIVE_SUBSCRIPTION_STATUSES:
        return True
    if member.stripe_customer_id:
        listing = stripe.Subscription.list(customer=member.stripe_customer_id, status='all', limit=20)
        return any(item.get('status') in LIVE_SUBSCRIPTION_STATUSES for item in listing.auto_paging_iter())
    return False


# 站上語言碼 → Stripe Checkout 的 locale。付款頁本身也要跟著使用者的語言，
# 否則使用者在 /zh/ 點購買、卻落到英文的 Stripe 頁面。
# 站上的 zh 翻譯是繁體（見 translation 的 zh 字串），所以對應 zh-TW 而不是 zh
# （Stripe 的 zh 是簡體）。新增站上語言時這裡要一起補，沒列到就退回 'auto'
# （由 Stripe 依瀏覽器判斷）而不是送出一個 Stripe 不認得的值導致整張 session 建立失敗。
STRIPE_LOCALES = {
    'en': 'en', 'zh': 'zh-TW', 'ja': 'ja', 'de': 'de', 'fr': 'fr', 'es': 'es',
}


@beta_closed
@login_required
def create_checkout_session(request):
    if request.method == 'POST':
        try:
            from django.utils import translation

            # /commerce/ 不在 i18n_patterns 底下，這裡啟動的語言永遠是英文；
            # 要在使用者的語言下組網址，success / cancel 才不會被帶回英文版。
            # 原本 success_url 是寫死的 '/'，連語言前綴都沒有。
            lang = _page_lang(request)
            with translation.override(lang):
                home_url = reverse('home')
                membership_url = reverse('account:membership')

            # 伺服器端擋重複訂閱：前端藏按鈕擋不住直接 POST，重複購買會雙重扣款
            if _has_live_subscription(request.user.member):
                messages.info(request, _text(
                    request, 'membership.subscription.msg.already',
                    'You already have an active subscription.', lang))
                return redirect(membership_url)

            response, consent = prepare_checkout(
                request, 'subscription', lang, back_url=membership_url,
            )
            if response is not None:
                return response

            # Prepare arguments
            kwargs = {
                'line_items': [
                    {
                        'price': settings.STRIPE_RECURRING_US699_PRICE_ID,
                        'quantity': 1,
                    },
                ],
                'mode': 'subscription',
                'success_url': request.build_absolute_uri(home_url) + '?session_id={CHECKOUT_SESSION_ID}',
                # 原本硬編碼 /tablejourney/membership/，那個網址從來不存在，
                # 使用者在 Stripe 按取消會落到 404。
                'cancel_url': request.build_absolute_uri(membership_url),
                'locale': STRIPE_LOCALES.get(lang, 'auto'),
                'client_reference_id': str(request.user.id),
                'metadata': consent_metadata(consent),
            }
            if request.user.member.stripe_customer_id:
                kwargs['customer'] = request.user.member.stripe_customer_id
            else:
                kwargs['customer_email'] = request.user.email

            checkout_session = stripe.checkout.Session.create(
                **kwargs, idempotency_key=f'checkout-consent-{consent.pk}',
            )
            consent.stripe_session_id = checkout_session.id
            consent.save(update_fields=['stripe_session_id'])
            return HttpResponseRedirect(checkout_session.url, status=303)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return HttpResponse(status=405)

EDITION_UNLOCK_KIND = 'edition_unlock'


@beta_closed
@login_required
def create_edition_unlock_session(request):
    """US$1 永久解鎖一款 Edition（一次性付款）。

    免費名額（見 member.EditionUnlock，預設 3 款）用完之後的加購入口。
    解鎖內容與免費名額完全相同：該 edition 流程圖的全螢幕／列印／步驟導覽、
    所有非入門 ruleset，以及該 edition 的 Rulesbot 無限查問。

    伺服器端一定要自己驗一次，不能只靠 info 頁不顯示按鈕——那顆按鈕藏不住
    直接 POST。四項驗證：
      1. 已登入（@login_required）
      2. edition 存在
      3. 尚未解鎖這款（避免重複收費）
      4. 這款有已發布流程圖。使用者定的規則：還沒有圖就不讓買，因為付了錢
         可能永遠拿不到東西，而付費解鎖是不可退回的。
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    from game.models import Edition
    from game.selectors import editions_with_published_flowchart

    from django.utils import translation

    lang = _page_lang(request)

    edition_id = (request.POST.get('edition_id') or '').strip()
    edition = Edition.objects.filter(id=edition_id).first() if edition_id else None
    if edition is None:
        messages.error(request, _unlock_msg(request, 'game.unlock.error.generic', lang))
        with translation.override(lang):
            return redirect('games:search')

    # 在使用者的語言下組網址，success_url / cancel_url / 錯誤導回才會帶 /zh/ 前綴
    with translation.override(lang):
        back_url = _edition_info_url(edition)
    member = request.user.member

    if member.has_unlocked(edition.id):
        # 已經有了就別再收一次錢，靜靜導回去即可
        return redirect(back_url)

    if not editions_with_published_flowchart([edition.id]):
        messages.error(request, _unlock_msg(request, 'game.unlock.error.no_flowchart', lang))
        return redirect(back_url)

    price_id = settings.STRIPE_FLOWCHART_SINGLE_EDITION_PRICE_ID
    if not price_id:
        logger.error("STRIPE_FLOWCHART_SINGLE_EDITION_PRICE_ID 未設定，無法建立加購 session")
        messages.error(request, _unlock_msg(request, 'game.unlock.error.generic', lang))
        return redirect(back_url)

    try:
        # metadata 是唯一能把「這筆錢買的是哪一款」帶回 webhook 的載體
        # （client_reference_id 只帶得動 user id）。session 與 payment_intent
        # 兩邊都寫，退款查帳時在 Stripe 後台才看得到買的是什麼。
        response, consent = prepare_checkout(
            request, EDITION_UNLOCK_KIND, lang, product_id=str(edition.id),
            product_label=str(edition), back_url=back_url,
        )
        if response is not None:
            return response
        meta = {'kind': EDITION_UNLOCK_KIND, 'edition_id': str(edition.id),
                **consent_metadata(consent)}
        kwargs = {
            'line_items': [{'price': price_id, 'quantity': 1}],
            'mode': 'payment',
            'client_reference_id': str(request.user.id),
            'metadata': meta,
            'payment_intent_data': {'metadata': meta},
            # {CHECKOUT_SESSION_ID} 由 Stripe 代換成真正的 session id，成功頁靠它
            # 向 Stripe 確認付款（見 fulfil_edition_unlock_from_session）
            'success_url': request.build_absolute_uri(back_url)
            + '?unlocked=1&session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': request.build_absolute_uri(back_url),
            'locale': STRIPE_LOCALES.get(lang, 'auto'),
        }
        if member.stripe_customer_id:
            kwargs['customer'] = member.stripe_customer_id
        else:
            kwargs['customer_email'] = request.user.email

        checkout_session = stripe.checkout.Session.create(
            **kwargs, idempotency_key=f'checkout-consent-{consent.pk}',
        )
        consent.stripe_session_id = checkout_session.id
        consent.save(update_fields=['stripe_session_id'])
        return HttpResponseRedirect(checkout_session.url, status=303)
    except Exception:
        logger.exception("建立 edition unlock checkout session 失敗 edition=%s", edition.id)
        messages.error(request, _unlock_msg(request, 'game.unlock.error.generic', lang))
        return redirect(back_url)


def _edition_info_url(edition):
    """該 edition 的 info 分頁——星星與購買入口所在的頁面（預設分頁，無後綴網址）。"""
    return edition.get_absolute_url()


def _unlock_msg(request, key, lang=None):
    """翻譯表查不到就退回 key 本身，與 {% t %} 的行為一致。

    lang 沒給就用 request.lang。/commerce/ 底下 request.lang 來自 session 而不是
    網址，與使用者正在看的頁面語言不一定一致，所以這個 view 一律明確傳 lang。
    """
    from translation.models import Translation, Tribe
    try:
        tribe = Tribe.objects.get(language=lang or getattr(request, 'lang', 'en'))
        return Translation.objects.get(tribe=tribe, key=key).value
    except Exception:
        return key


def _page_lang(request):
    """使用者是從哪個語言的頁面送出這次請求的。

    /commerce/ 不在 i18n_patterns 裡（見 translation/middleware.py 的
    UNPREFIXED_PATHS），所以這個 view 啟動的語言永遠是預設的英文，
    edition.get_absolute_url() 因此組不出 /zh/ 這種前綴——付款完成後使用者被
    導回英文版。語言必須從別處取得，依序：
      1. 表單帶來的 lang 欄位（頁面自己知道自己的語言，最可靠）
      2. Referer 的網址前綴（沒帶欄位的舊表單、或直接 POST）
      3. 預設語言
    1 與 2 都要過 SUPPORTED_LANGS 白名單：這個值最後會進 reverse()，不能讓
    使用者塞任意字串。
    """
    from urllib.parse import urlparse

    from django.utils import translation
    from translation.middleware import DEFAULT_LANG, SUPPORTED_LANGS

    lang = (request.POST.get('lang') or '').strip()
    if lang in SUPPORTED_LANGS:
        return lang

    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        from_path = translation.get_language_from_path(urlparse(referer).path)
        if from_path in SUPPORTED_LANGS:
            return from_path
    return DEFAULT_LANG


def _ensure_transaction(session, member, payment_intent_id=None, invoice_id=None):
    """用 checkout session 建立（或取回）對應的 Transaction。

    payment_intent_id / invoice_id 給了就蓋過 session 裡的值：訂閱模式的
    session 常常沒帶 invoice，webhook 會另外向 Stripe 補查（見
    stripe_webhook 的 subscription 分支），補查到的值要能傳進來，不然訂閱的
    交易紀錄會比重構前少欄位。單品付款不需要，用 session 自己的值即可。

    get_or_create 而非 create：Stripe 會重送事件，而 stripe_session_id 有
    unique 約束，create 在重送時會拋 IntegrityError。webhook 與成功頁的補發
    （fulfil_edition_unlock_from_session）兩條路徑都可能處理同一筆付款，
    誰先到誰建立、後到的取回既有那筆，兩邊都不會重複或報錯。
    """
    txn, _ = Transaction.objects.get_or_create(
        stripe_session_id=session.get('id'),
        defaults={
            'member': member,
            'payment_intent_id': payment_intent_id or session.get('payment_intent'),
            'invoice_id': invoice_id or session.get('invoice'),
            'customer_id': session.get('customer'),
            'amount': (session.get('amount_total') or 0) / 100.0,
            'currency': session.get('currency') or '',
            'status': 'complete',
        },
    )
    return txn


def fulfil_edition_unlock_from_session(member, edition, session_id):
    """付款完成後導回成功頁時，主動向 Stripe 確認並補發解鎖。回傳是否已解鎖。

    webhook 才是正式的發放管道，但它依賴 Stripe 能打到我們（開發時還要
    stripe listen 開著）；使用者付完錢回到頁面時看到「沒變化」是最糟的體驗。
    這裡是第二條、冪等的路徑：與 webhook 共用 _ensure_transaction /
    _grant_edition_unlock，所以兩邊誰先到都一樣，不會重複發放。

    **不能信任網址上的任何東西**，所以要向 Stripe 取回 session 再逐項核對：
      - 已付款（payment_status == 'paid'）
      - client_reference_id 就是目前登入的會員——否則拿別人的 session id 就能
        替自己發放解鎖
      - metadata 的 kind / edition_id 與這一頁的 edition 相符——否則拿便宜
        版本的付款單去解鎖別款
    任何一項不符都當作沒付款，回傳 False，不報錯給使用者看。
    """
    if member.has_unlocked(edition.id):
        return True
    if not session_id:
        return False

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        logger.exception("成功頁補發：向 Stripe 取回 session 失敗 session=%s", session_id)
        return False

    meta = session.get('metadata') or {}
    if (
        session.get('payment_status') != 'paid'
        or str(session.get('client_reference_id')) != str(member.pk)
        or meta.get('kind') != EDITION_UNLOCK_KIND
        or str(meta.get('edition_id')) != str(edition.id)
    ):
        return False

    try:
        confirm_paid_checkout(session)
    except Exception:
        logger.exception("Checkout confirmation failed; awaiting webhook retry session=%s", session_id)
        return False
    try:
        txn = _ensure_transaction(session, member)
        _grant_edition_unlock(session, member, txn)
    except Exception:
        # 已記 log 並通知；webhook 重試會補發，這裡別讓成功頁 500
        return False
    member.invalidate_unlocked_cache()
    return member.has_unlocked(edition.id)


def _grant_edition_unlock(session, member, txn):
    """付款完成 → 建立 source='paid' 的 EditionUnlock。

    包在自己的 try 裡：付了錢沒拿到東西是最不能靜默的失敗模式，而外層那個
    blanket except 正好會讓它變靜默。真的失敗時要 log 到查得出是哪一筆。

    get_or_create 讓 Stripe 重送事件時冪等。若該會員已經用免費名額選過同一款
    （購買前驗證擋得掉，但競態下仍可能發生），既有的 free 列會被保留、不會被
    改寫成 paid——結果對使用者無害，但等於收了錢沒給對應的東西，所以要
    log warning 讓人工退款。
    """
    meta = session.get('metadata') or {}
    if meta.get('kind') != EDITION_UNLOCK_KIND:
        return

    edition_id = meta.get('edition_id')
    if not edition_id:
        logger.error(
            "edition_unlock 付款缺少 metadata.edition_id，session=%s member=%s",
            session.get('id'), member.pk,
        )
        return

    try:
        from member.models import EditionUnlock
        unlock, created = EditionUnlock.objects.get_or_create(
            member=member, edition_id=edition_id,
            defaults={'source': EditionUnlock.Source.PAID, 'transaction': txn},
        )
        if not created and unlock.source != EditionUnlock.Source.PAID:
            logger.warning(
                "edition_unlock 付款對象已有免費解鎖，可能需要人工退款："
                "session=%s member=%s edition=%s",
                session.get('id'), member.pk, edition_id,
            )
    except Exception:
        logger.exception(
            "edition_unlock 建立失敗（已收款！）session=%s member=%s edition=%s",
            session.get('id'), member.pk, edition_id,
        )
        _alert_admin(
            'Edition unlock failed after payment',
            f'session={session.get("id")} member={member.pk} edition={edition_id}',
        )
        # 往外拋：webhook 會回 500 讓 Stripe 重試（get_or_create 冪等）
        raise


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        return HttpResponse(status=400)
    except Exception as e:
        return HttpResponse(status=400)

    if event['type'] in ('checkout.session.completed', 'checkout.session.async_payment_succeeded'):
        session = event['data']['object']
        if session.get('payment_status') not in ('paid', 'no_payment_required'):
            return HttpResponse(status=200)
        try:
            confirm_paid_checkout(session)
        except Exception:
            logger.exception('Checkout confirmation failed for event %s', event.get('id'))
            return HttpResponse(status=500)
        
        client_reference_id = session.get('client_reference_id')
        customer_id = session.get('customer')
        payment_intent_id = session.get('payment_intent')
        invoice_id = session.get('invoice')
        
        if client_reference_id:
            try:
                member = Member.objects.get(id=client_reference_id)

                # ⚠️ tier 升級只在訂閱模式發生。以前這裡沒有判斷 mode，對任何
                # checkout session 都把人升成 subscriber——加入 US$1 單品加購
                # （mode='payment'）之後，那會變成每買一款 edition 就白送一份
                # 完整訂閱權限。
                if session.get('mode') == 'subscription':
                    try:
                        tier_sub = Tier.objects.get(code='subscriber')
                        member.tier_new = tier_sub
                    except Tier.DoesNotExist:
                        pass

                # customer id 兩種模式都要記：單品付款也會產生／沿用同一個
                # Stripe customer，之後開訂閱時才不會又開一個新的。
                if customer_id:
                    member.stripe_customer_id = customer_id
                member.save()

                payment_intent_id = session.get('payment_intent')
                invoice_id = session.get('invoice')

                # Update or create subscription record
                if session.get('mode') == 'subscription':
                    sub_id = session.get('subscription')
                    if sub_id:
                        sub = stripe.Subscription.retrieve(sub_id)
                        
                        # Fallback for invoice_id if the session object doesn't have it
                        if not invoice_id:
                            invoice_id = sub.get('latest_invoice')
                            
                            # Retrieve the invoice to get payment_intent_id
                            if invoice_id and not payment_intent_id:
                                try:
                                    # Handle stripe invoice being expanded or just ID
                                    inv_id_str = invoice_id if isinstance(invoice_id, str) else invoice_id.get('id')
                                    inv = stripe.Invoice.retrieve(inv_id_str)
                                    payment_intent_id = inv.get('payment_intent')
                                except Exception:
                                    pass
                        
                        # Try to get dates from root, fallback to items.data[0]
                        period_start = sub.get('current_period_start')
                        period_end = sub.get('current_period_end')
                        
                        if not period_start or not period_end:
                            items_data = sub.get('items', {}).get('data', [])
                            if items_data:
                                period_start = period_start or items_data[0].get('current_period_start')
                                period_end = period_end or items_data[0].get('current_period_end')
                        
                        if not period_start:
                            period_start = 0
                        if not period_end:
                            period_end = 0
                            
                        # 已有另一份有效訂閱時（入口擋不住的競態），不能覆蓋舊的紀錄：
                        # 舊訂閱在 Stripe 仍會續扣。保留舊紀錄、通知人工退掉其中一份。
                        existing = Subscription.objects.filter(member=member).first()
                        if (existing and existing.stripe_subscription_id != sub_id
                                and existing.status in LIVE_SUBSCRIPTION_STATUSES):
                            _alert_admin(
                                'Duplicate subscription paid',
                                f'member={member.pk} already has {existing.stripe_subscription_id} '
                                f'({existing.status}); new {sub_id} was NOT recorded. '
                                'Cancel/refund one of them in Stripe.',
                            )
                            return HttpResponse(status=200)

                        # Use update_or_create keyed on member since it's a OneToOneField
                        Subscription.objects.update_or_create(
                            member=member,
                            defaults={
                                'stripe_subscription_id': sub_id,
                                'status': sub.get('status'),
                                'current_period_start': datetime.datetime.fromtimestamp(period_start, tz=datetime.timezone.utc),
                                'current_period_end': datetime.datetime.fromtimestamp(period_end, tz=datetime.timezone.utc),
                                'cancel_at_period_end': sub.get('cancel_at_period_end', False)
                            }
                        )
                
                txn = _ensure_transaction(
                    session, member,
                    payment_intent_id=payment_intent_id, invoice_id=invoice_id,
                )

                _grant_edition_unlock(session, member, txn)
            except Member.DoesNotExist:
                # 重送也不會自己好，回 200 避免無限重試；但已收款，必須通知人工處理。
                logger.error("checkout 付款對應不到 Member client_reference_id=%s", client_reference_id)
                _alert_admin(
                    'Paid checkout has no matching member',
                    f'event={event.get("id")} session={session.get("id")} '
                    f'client_reference_id={client_reference_id}. Customer paid but nobody was provisioned.',
                )
            except Exception:
                # 回 500 讓 Stripe 重試（開通動作皆冪等），並通知人工，
                # 不能再回 200：那會變成「已扣款、未開通、Stripe 不再重試」。
                logger.exception(
                    "Failed to process checkout.session.completed for event %s",
                    event.get('id')
                )
                _alert_admin(
                    'Provisioning failed after payment (Stripe will retry)',
                    f'event={event.get("id")} session={session.get("id")} '
                    f'member={client_reference_id}. See server log for the traceback.',
                )
                return HttpResponse(status=500)

    elif event['type'] in ['customer.subscription.updated', 'customer.subscription.deleted']:
        subscription_obj = event['data']['object']
        sub_id = subscription_obj.get('id')
        
        try:
            sub = Subscription.objects.get(stripe_subscription_id=sub_id)
            sub.status = subscription_obj.get('status')
            
            period_start = subscription_obj.get('current_period_start')
            period_end = subscription_obj.get('current_period_end')
            
            if not period_start or not period_end:
                items_data = subscription_obj.get('items', {}).get('data', [])
                if items_data:
                    period_start = period_start or items_data[0].get('current_period_start')
                    period_end = period_end or items_data[0].get('current_period_end')
                    
            if not period_start:
                period_start = 0
            if not period_end:
                period_end = 0
                
            sub.current_period_start = datetime.datetime.fromtimestamp(period_start, tz=datetime.timezone.utc)
            sub.current_period_end = datetime.datetime.fromtimestamp(period_end, tz=datetime.timezone.utc)
            sub.cancel_at_period_end = subscription_obj.get('cancel_at_period_end', False)
            sub.save()
            
            # Downgrade if the subscription is no longer active
            if sub.status in ['canceled', 'unpaid', 'incomplete_expired']:
                member = sub.member
                try:
                    tier_free = Tier.objects.get(code='free')
                    member.tier_new = tier_free
                except Tier.DoesNotExist:
                    pass
                member.save()
            elif sub.status in ('active', 'trialing'):
                # 欠款（unpaid）後補繳恢復 active 時要把權限還回來；
                # past_due 是 Stripe 的重試寬限期，維持現有權限不動。
                member = sub.member
                tier_sub = Tier.objects.filter(code='subscriber').first()
                if tier_sub and member.tier_new_id != tier_sub.id:
                    member.tier_new = tier_sub
                    member.save()

        except Subscription.DoesNotExist:
            pass
        except Exception:
            logger.exception('Failed to process %s for event %s', event['type'], event.get('id'))
            _alert_admin('Subscription sync failed (Stripe will retry)',
                         f'event={event.get("id")} subscription={sub_id}')
            return HttpResponse(status=500)

    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        sub_id = invoice.get('subscription')
        try:
            sub = Subscription.objects.get(stripe_subscription_id=sub_id)
        except Subscription.DoesNotExist:
            return HttpResponse(status=200)
        except Exception:
            logger.exception('invoice.payment_failed lookup failed event=%s', event.get('id'))
            return HttpResponse(status=500)
        sub.status = 'past_due'
        sub.save(update_fields=['status', 'updated_at'])
        _alert_admin('Subscription renewal payment failed',
                     f'member={sub.member_id} subscription={sub_id} invoice={invoice.get("id")}')
        # 通知會員去更新付款方式；寄信失敗不影響 webhook（Stripe 本身也會寄催繳信）
        try:
            user = sub.member.id
            if user.email:
                send_mail(
                    'Tabuney — your subscription payment failed',
                    'We could not charge your payment method for your Tabuney subscription. '
                    'Please update your payment method on the membership page to keep your access. '
                    'Stripe will retry the payment automatically for a few days.',
                    settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
                )
        except Exception:
            logger.exception('payment_failed notice email failed member=%s', sub.member_id)

    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        # Only log a new transaction for recurring cycles. The initial one is logged by checkout.session.completed.
        if invoice.get('billing_reason') == 'subscription_cycle':
            customer_id = invoice.get('customer')
            sub_id = invoice.get('subscription')
            amount_paid = invoice.get('amount_paid', 0) / 100.0
            currency = invoice.get('currency', '')
            payment_intent_id = invoice.get('payment_intent')
            invoice_id = invoice.get('id')
            
            try:
                sub = Subscription.objects.get(stripe_subscription_id=sub_id)
                # Create the transaction for auto-renewal
                if not Transaction.objects.filter(invoice_id=invoice_id).exists():
                    Transaction.objects.create(
                        member=sub.member,
                        stripe_session_id=f"recurring_{invoice_id}",
                        payment_intent_id=payment_intent_id,
                        invoice_id=invoice_id,
                        customer_id=customer_id,
                        amount=amount_paid,
                        currency=currency,
                        status='complete'
                    )
            except Subscription.DoesNotExist:
                pass

    return HttpResponse(status=200)

def _set_cancel_at_period_end(request, cancel):
    """取消／恢復自動續訂。Stripe 成功才改本地，並明確告訴使用者成敗。"""
    from django.utils import translation
    lang = _page_lang(request)
    sub = getattr(request.user.member, 'subscription', None)
    if request.method == 'POST' and sub and sub.stripe_subscription_id             and sub.cancel_at_period_end != cancel:
        try:
            stripe_sub = stripe.Subscription.modify(
                sub.stripe_subscription_id, cancel_at_period_end=cancel,
            )
            sub.cancel_at_period_end = bool(stripe_sub.get('cancel_at_period_end', cancel))
            sub.save(update_fields=['cancel_at_period_end', 'updated_at'])
            messages.success(request, _text(
                request, 'membership.subscription.msg.cancelled' if cancel else 'membership.subscription.msg.resumed',
                'Auto-renewal is turned off. Your access continues until the end of the current period.'
                if cancel else 'Auto-renewal is turned back on.', lang))
        except Exception:
            logger.exception('Subscription cancel_at_period_end=%s failed member=%s', cancel, request.user.pk)
            messages.error(request, _text(
                request, 'membership.subscription.msg.error',
                'Something went wrong and your subscription was not changed. Please try again later or contact info@tabuney.com.',
                lang))
    with translation.override(lang):
        return redirect('account:membership')


@login_required
def cancel_subscription(request):
    return _set_cancel_at_period_end(request, True)


@login_required
def resume_subscription(request):
    return _set_cancel_at_period_end(request, False)


@login_required
def billing_portal(request):
    """導向 Stripe Customer Portal，讓會員更新付款方式（續費失敗時用）。"""
    from django.utils import translation
    lang = _page_lang(request)
    with translation.override(lang):
        membership_url = reverse('account:membership')
    customer_id = request.user.member.stripe_customer_id
    if request.method == 'POST' and customer_id:
        try:
            portal = stripe.billing_portal.Session.create(
                customer=customer_id, return_url=request.build_absolute_uri(membership_url),
            )
            return HttpResponseRedirect(portal.url, status=303)
        except Exception:
            logger.exception('Billing portal creation failed member=%s', request.user.pk)
            messages.error(request, _text(
                request, 'membership.subscription.msg.error',
                'Something went wrong. Please try again later or contact info@tabuney.com.', lang))
    return redirect(membership_url)
