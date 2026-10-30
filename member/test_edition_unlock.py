"""Per-edition 永久解鎖：免費 3 款 + US$1 加購。

涵蓋四組不變式：
  1. 名額 —— 免費名額用得完、付費不佔名額、重複選不會多佔
  2. 退回 —— 只有「沒有已發布流程圖 + source=free」的列退得回
  3. 權限範圍 —— 只解鎖選定的那一款，且與 tier 脫鉤（降級不失效）
  4. 金流 —— mode='payment' 絕不升 tier、webhook 重送要冪等

第 4 組是重點：stripe_webhook 原本對任何 checkout.session.completed 都無條件
把人升成 subscriber，加入 US$1 單品之後那等於每買一款就白送一份訂閱。
"""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from commerce.models import Transaction
from game.models import Edition, Game, Rulebook, RulebookFlowchart
from game.tests.flowchart_helpers import publish_flowchart
from game.views.chat_views import get_chat_limits
from translation.models import Tribe

from .models import EditionUnlock, Member, Tier

# member app 的 migration 只 seed 了 code='free'；其餘 tier 是正式環境手動建立的，
# 測試 DB 不會有，所以一律自己 create。


def _chart_json():
    """非空的 react_flow_json —— 空圖（{}）不算「有流程圖」。"""
    return {"nodes": [{"id": "n1", "data": {"label": "Start"}}], "edges": []}


class EditionUnlockTestBase(TestCase):
    def setUp(self):
        # Member.tribe 預設 default=1，建立 User 的 signal 會用到，先確保存在
        self.tribe, _ = Tribe.objects.get_or_create(
            pk=1, defaults={"language": "en", "name": "English"},
        )
        self.free_tier = Tier.objects.create(
            code="test_free", name="Test Free",
            limits={
                "edition_unlock": 3,
                "flowchart_non_initial": 0,
                "flowchart_print": 0,
                "flowchart_fullscreen": 0,
                "flowchart_tour": 0,
                "script": 0,
                "prompt_per_week": 5,
            },
        )
        self.user = User.objects.create_user(username="u1", password="pw")
        self.member = Member.objects.get(id=self.user.id)
        self.member.tier_new = self.free_tier
        self.member.save()
        # 建立 User 的 post_save signal 會存取 instance.member，把當時還沒有
        # tier 的 Member 快取在 User 實例上。不重新取一份的話，後面凡是走
        # user.member 的程式碼（get_chat_limits 等）都會讀到 tier_new=None。
        self.user = User.objects.get(pk=self.user.pk)

        self.game = Game.objects.create(canonical_name="Test Game")

    def make_edition(self, name, with_flowchart=True, initial=True, published=True):
        edition = Edition.objects.create(game=self.game, name=name)
        if with_flowchart:
            rulebook = Rulebook.objects.create(edition=edition, language=self.tribe)
            chart = RulebookFlowchart.objects.create(
                rulebook=rulebook, edition=edition, ruleset="basic",
                react_flow_json=_chart_json(), initial=initial,
            )
            if published:
                publish_flowchart(chart)
        return edition

    def fresh_member(self):
        """重新讀一份 Member，確保讀到的不是實例上的解鎖快取。"""
        return Member.objects.get(pk=self.member.pk)


class FreeQuotaTests(EditionUnlockTestBase):
    def test_free_picks_are_capped(self):
        for i in range(3):
            EditionUnlock.objects.create(
                member=self.member, edition=self.make_edition(f"E{i}"),
                source=EditionUnlock.Source.FREE,
            )
        member = self.fresh_member()
        self.assertEqual(member.free_unlock_usage(), (3, 3))
        self.assertFalse(member.can_pick_free())

    def test_paid_unlocks_do_not_consume_free_quota(self):
        EditionUnlock.objects.create(
            member=self.member, edition=self.make_edition("paid"),
            source=EditionUnlock.Source.PAID,
        )
        member = self.fresh_member()
        self.assertEqual(member.free_unlock_usage(), (0, 3))
        self.assertTrue(member.can_pick_free())

    def test_pick_view_rejects_fourth_free_pick(self):
        client = Client()
        client.force_login(self.user)
        for i in range(3):
            EditionUnlock.objects.create(
                member=self.member, edition=self.make_edition(f"E{i}"),
                source=EditionUnlock.Source.FREE,
            )
        fourth = self.make_edition("fourth")
        client.post(reverse("account:unlock-pick"), {"edition_id": str(fourth.id)})

        self.assertEqual(EditionUnlock.objects.filter(member=self.member).count(), 3)
        self.assertFalse(
            EditionUnlock.objects.filter(member=self.member, edition=fourth).exists()
        )

    def test_picking_same_edition_twice_uses_one_slot(self):
        client = Client()
        client.force_login(self.user)
        edition = self.make_edition("same")
        url = reverse("account:unlock-pick")
        client.post(url, {"edition_id": str(edition.id)})
        client.post(url, {"edition_id": str(edition.id)})

        self.assertEqual(EditionUnlock.objects.filter(member=self.member).count(), 1)
        self.assertEqual(self.fresh_member().free_unlock_usage(), (1, 3))

    def test_anonymous_cannot_pick(self):
        edition = self.make_edition("anon")
        Client().post(reverse("account:unlock-pick"), {"edition_id": str(edition.id)})
        self.assertEqual(EditionUnlock.objects.count(), 0)


class ReleaseTests(EditionUnlockTestBase):
    def setUp(self):
        super().setUp()
        self.client_ = Client()
        self.client_.force_login(self.user)

    def test_release_allowed_when_no_published_flowchart(self):
        edition = self.make_edition("no-chart", with_flowchart=False)
        EditionUnlock.objects.create(member=self.member, edition=edition)

        self.client_.post(reverse("account:unlock-release"), {"edition_id": str(edition.id)})

        self.assertFalse(EditionUnlock.objects.filter(edition=edition).exists())
        self.assertEqual(self.fresh_member().free_unlock_usage(), (0, 3))

    def test_release_allowed_when_flowchart_unpublished(self):
        # 有圖但未發布 → 使用者看不到，等同還沒有圖
        edition = self.make_edition("draft", published=False)
        EditionUnlock.objects.create(member=self.member, edition=edition)

        self.client_.post(reverse("account:unlock-release"), {"edition_id": str(edition.id)})

        self.assertFalse(EditionUnlock.objects.filter(edition=edition).exists())

    def test_release_rejected_once_flowchart_published(self):
        edition = self.make_edition("locked-in")
        EditionUnlock.objects.create(member=self.member, edition=edition)

        self.client_.post(reverse("account:unlock-release"), {"edition_id": str(edition.id)})

        self.assertTrue(EditionUnlock.objects.filter(edition=edition).exists())

    def test_release_rejected_for_paid_unlock(self):
        # 付費列就算該版本沒有圖也不可退回（購買前就擋掉了這種 edition，
        # 這裡是防禦性檢查）
        edition = self.make_edition("paid-no-chart", with_flowchart=False)
        EditionUnlock.objects.create(
            member=self.member, edition=edition, source=EditionUnlock.Source.PAID,
        )

        self.client_.post(reverse("account:unlock-release"), {"edition_id": str(edition.id)})

        self.assertTrue(EditionUnlock.objects.filter(edition=edition).exists())


class FlowchartPermissionTests(EditionUnlockTestBase):
    """解鎖只作用於選定的那一款，且不隨 tier 降級失效。"""

    def _flowchart_context(self, edition):
        client = Client()
        client.force_login(self.user)
        return client.get(f"{edition.get_absolute_url()}flowchart/")

    def test_unlocked_edition_opens_all_four_capabilities(self):
        edition = self.make_edition("unlocked", initial=False)
        EditionUnlock.objects.create(member=self.member, edition=edition)

        ctx = self._flowchart_context(edition).context
        self.assertTrue(ctx["can_flowchart_fullscreen"])
        self.assertTrue(ctx["can_flowchart_print"])
        self.assertTrue(ctx["can_flowchart_tour"])
        # 非入門圖要解得開，而且內容要真的進得了 viewer configs
        self.assertFalse(ctx["flowchart_charts"][0]["locked"])
        self.assertEqual(len(ctx["flowchart_viewer_configs"]), 1)

    def test_other_edition_stays_locked(self):
        unlocked = self.make_edition("A", initial=False)
        other = self.make_edition("B", initial=False)
        EditionUnlock.objects.create(member=self.member, edition=unlocked)

        ctx = self._flowchart_context(other).context
        self.assertFalse(ctx["can_flowchart_fullscreen"])
        self.assertFalse(ctx["can_flowchart_print"])
        self.assertFalse(ctx["can_flowchart_tour"])
        self.assertTrue(ctx["flowchart_charts"][0]["locked"])
        # 鎖住的圖內容不得進頁面原始碼
        self.assertEqual(ctx["flowchart_viewer_configs"], [])
        self.assertIsNone(ctx["flowchart_charts"][0]["outline"])

    def test_unlock_survives_tier_downgrade(self):
        sub = Tier.objects.create(
            code="test_sub", name="Sub",
            limits={"flowchart_non_initial": 1, "flowchart_print": 1,
                    "flowchart_fullscreen": 1, "flowchart_tour": 1},
        )
        edition = self.make_edition("kept", initial=False)
        self.member.tier_new = sub
        self.member.save()
        EditionUnlock.objects.create(member=self.member, edition=edition)

        # 會籍過期 → 降回沒有任何流程圖 feature 的 tier
        self.member.tier_new = self.free_tier
        self.member.save()

        ctx = self._flowchart_context(edition).context
        self.assertTrue(ctx["can_flowchart_print"])
        self.assertFalse(ctx["flowchart_charts"][0]["locked"])

    def test_script_stays_subscriber_only(self):
        """解鎖不含 GM 講稿——講稿仍只看 tier feature 'script'。"""
        edition = self.make_edition("with-script")
        EditionUnlock.objects.create(member=self.member, edition=edition)

        client = Client()
        client.force_login(self.user)
        resp = client.get(f"{edition.get_absolute_url()}")
        # info 頁的 unlock 區塊要認得這是已解鎖，但 script 權限不受影響
        self.assertTrue(resp.context["unlock_is_picked"])
        self.assertFalse(self.fresh_member().can("script"))


class RulesbotQuotaTests(EditionUnlockTestBase):
    def test_unlocked_edition_is_unlimited(self):
        edition = self.make_edition("chatty")
        EditionUnlock.objects.create(member=self.member, edition=edition)

        limits = get_chat_limits(self.user, edition.id)
        self.assertEqual(limits["total"], -1)
        self.assertEqual(limits["remaining"], -1)

    def test_other_edition_keeps_weekly_quota(self):
        unlocked = self.make_edition("A")
        other = self.make_edition("B")
        EditionUnlock.objects.create(member=self.member, edition=unlocked)

        limits = get_chat_limits(self.user, other.id)
        self.assertEqual(limits["total"], 5)
        self.assertEqual(limits["remaining"], 5)

    def test_unlocked_usage_does_not_eat_other_editions_quota(self):
        """「無限」如果還會侵蝕別處的配額，那就不是無限。"""
        from game.models import ChatMessage, ChatSession

        unlocked = self.make_edition("A")
        other = self.make_edition("B")
        EditionUnlock.objects.create(member=self.member, edition=unlocked)

        session = ChatSession.objects.create(edition=unlocked, user=self.user)
        for _ in range(4):
            ChatMessage.objects.create(session=session, role="user", content="q")

        self.assertEqual(get_chat_limits(self.user, other.id)["remaining"], 5)

        # 對照組：未解鎖 edition 的訊息照樣計入
        other_session = ChatSession.objects.create(edition=other, user=self.user)
        ChatMessage.objects.create(session=other_session, role="user", content="q")
        self.assertEqual(get_chat_limits(self.user, other.id)["remaining"], 4)


class StripeWebhookTests(EditionUnlockTestBase):
    """US$1 單品加購的 webhook 行為。"""

    def _session(self, edition, mode="payment", session_id="cs_test_1"):
        return {
            "id": session_id,
            "mode": mode,
            "client_reference_id": str(self.user.id),
            "customer": "cus_test",
            "payment_intent": "pi_test",
            "invoice": None,
            "amount_total": 100,
            "currency": "usd",
            "metadata": {"kind": "edition_unlock", "edition_id": str(edition.id)},
        }

    def _post_event(self, session):
        event = {"id": "evt_test", "type": "checkout.session.completed",
                 "data": {"object": session}}
        with patch("stripe.Webhook.construct_event", return_value=event):
            return self.client.post(
                reverse("commerce:stripe-webhook"),
                data=json.dumps(event), content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=fake",
            )

    def test_one_time_payment_does_not_grant_subscriber_tier(self):
        Tier.objects.create(code="subscriber", name="Subscriber", limits={})
        edition = self.make_edition("bought")

        self._post_event(self._session(edition))

        self.member.refresh_from_db()
        self.assertEqual(self.member.tier_new.code, "test_free")

    def test_one_time_payment_creates_paid_unlock(self):
        edition = self.make_edition("bought")

        self._post_event(self._session(edition))

        unlock = EditionUnlock.objects.get(member=self.member, edition=edition)
        self.assertEqual(unlock.source, EditionUnlock.Source.PAID)
        self.assertIsNotNone(unlock.transaction)
        self.assertEqual(unlock.transaction.stripe_session_id, "cs_test_1")

    def test_replayed_event_is_idempotent(self):
        edition = self.make_edition("bought")
        session = self._session(edition)

        self._post_event(session)
        resp = self._post_event(session)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Transaction.objects.filter(stripe_session_id="cs_test_1").count(), 1)
        self.assertEqual(EditionUnlock.objects.filter(edition=edition).count(), 1)

    def test_subscription_mode_still_upgrades_tier(self):
        """回歸測試：加了 mode 判斷之後，訂閱那條路不能壞掉。"""
        Tier.objects.create(code="subscriber", name="Subscriber", limits={})
        session = {
            "id": "cs_sub_1", "mode": "subscription",
            "client_reference_id": str(self.user.id),
            "customer": "cus_test", "payment_intent": "pi_test", "invoice": None,
            "amount_total": 699, "currency": "usd",
            "subscription": None,  # 沒有 sub_id -> 跳過 Subscription 建立
            "metadata": {},
        }
        self._post_event(session)

        self.member.refresh_from_db()
        self.assertEqual(self.member.tier_new.code, "subscriber")


class PurchaseGuardTests(EditionUnlockTestBase):
    """送去 Stripe 之前的伺服器端驗證（按鈕藏不住直接 POST）。"""

    def setUp(self):
        super().setUp()
        self.client_ = Client()
        self.client_.force_login(self.user)
        self.url = reverse("commerce:create-edition-unlock-session")

    @patch("stripe.checkout.Session.create")
    def test_rejects_edition_without_published_flowchart(self, mock_create):
        edition = self.make_edition("no-chart", with_flowchart=False)
        self.client_.post(self.url, {"edition_id": str(edition.id)})
        mock_create.assert_not_called()

    @patch("stripe.checkout.Session.create")
    def test_rejects_already_unlocked_edition(self, mock_create):
        edition = self.make_edition("owned")
        EditionUnlock.objects.create(member=self.member, edition=edition)
        self.client_.post(self.url, {"edition_id": str(edition.id)})
        mock_create.assert_not_called()

    @patch("stripe.checkout.Session.create")
    def test_creates_session_with_edition_metadata(self, mock_create):
        mock_create.return_value = type("S", (), {"url": "https://stripe.test/pay"})()
        edition = self.make_edition("buyable")

        with self.settings(STRIPE_FLOWCHART_SINGLE_EDITION_PRICE_ID="price_test"):
            self.client_.post(self.url, {"edition_id": str(edition.id)})

        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["mode"], "payment")
        self.assertEqual(kwargs["metadata"]["kind"], "edition_unlock")
        self.assertEqual(kwargs["metadata"]["edition_id"], str(edition.id))
        self.assertEqual(kwargs["line_items"][0]["price"], "price_test")


class SuccessPageReturnTests(EditionUnlockTestBase):
    """付款完成導回 ?unlocked=1&session_id=… 時的補發與提示。

    webhook 沒到時使用者不能看到「沒變化」。成功頁會向 Stripe 取回 session
    並補發，但網址是使用者可控的，所以重點是濫用情境：別人的付款單、別款的
    付款單、沒付款的單，都不能替自己發放解鎖。
    """

    def setUp(self):
        super().setUp()
        self.edition = self.make_edition("returned")
        self.client_ = Client()
        self.client_.force_login(self.user)
        # force_login 會更新 last_login，觸發 User post_save，而那個 signal 會
        # 用建立時快取的 Member 把 tier 洗掉——tier 要在登入之後再設。
        self.member = Member.objects.get(pk=self.member.pk)
        self.member.tier_new = self.free_tier
        self.member.save()

    def _session(self, **over):
        s = {
            "id": "cs_test_return",
            "payment_status": "paid",
            "client_reference_id": str(self.user.id),
            "customer": "cus_x", "payment_intent": "pi_x", "invoice": None,
            "amount_total": 100, "currency": "usd",
            "metadata": {"kind": "edition_unlock", "edition_id": str(self.edition.id)},
        }
        s.update(over)
        return s

    def _return(self, session_id="cs_test_return", follow=True):
        url = f"{self.edition.get_absolute_url()}"
        return self.client_.get(url, {"unlocked": "1", "session_id": session_id}, follow=follow)

    def _msgs(self, resp):
        return [m.level_tag for m in resp.context["messages"]]

    @patch("stripe.checkout.Session.retrieve")
    def test_paid_session_grants_unlock_and_transaction(self, retrieve):
        retrieve.return_value = self._session()
        resp = self._return()

        unlock = EditionUnlock.objects.get(member=self.member, edition=self.edition)
        self.assertEqual(unlock.source, EditionUnlock.Source.PAID)
        self.assertEqual(unlock.transaction.stripe_session_id, "cs_test_return")
        self.assertIn("success", self._msgs(resp))

    @patch("stripe.checkout.Session.retrieve")
    def test_redirects_to_clean_url(self, retrieve):
        retrieve.return_value = self._session()
        resp = self._return(follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("session_id", resp["Location"])
        self.assertNotIn("unlocked", resp["Location"])

    @patch("stripe.checkout.Session.retrieve")
    def test_unpaid_session_is_not_granted(self, retrieve):
        retrieve.return_value = self._session(payment_status="unpaid")
        resp = self._return()
        self.assertFalse(EditionUnlock.objects.filter(member=self.member).exists())
        self.assertIn("warning", self._msgs(resp))

    @patch("stripe.checkout.Session.retrieve")
    def test_someone_elses_session_is_refused(self, retrieve):
        other = User.objects.create_user(username="other", password="pw")
        retrieve.return_value = self._session(client_reference_id=str(other.id))
        resp = self._return()
        self.assertFalse(EditionUnlock.objects.exists())
        self.assertIn("warning", self._msgs(resp))

    @patch("stripe.checkout.Session.retrieve")
    def test_session_for_a_different_edition_is_refused(self, retrieve):
        elsewhere = self.make_edition("different")
        retrieve.return_value = self._session(
            metadata={"kind": "edition_unlock", "edition_id": str(elsewhere.id)})
        self._return()
        self.assertFalse(EditionUnlock.objects.exists())

    @patch("stripe.checkout.Session.retrieve")
    def test_non_unlock_session_is_refused(self, retrieve):
        # 例如訂閱的 checkout session id 被拿來冒充
        retrieve.return_value = self._session(metadata={})
        self._return()
        self.assertFalse(EditionUnlock.objects.exists())

    @patch("stripe.checkout.Session.retrieve", side_effect=RuntimeError("stripe down"))
    def test_stripe_failure_degrades_to_pending(self, retrieve):
        resp = self._return()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(EditionUnlock.objects.exists())
        self.assertIn("warning", self._msgs(resp))

    @patch("stripe.checkout.Session.retrieve")
    def test_missing_session_id_never_calls_stripe(self, retrieve):
        resp = self._return(session_id="")
        retrieve.assert_not_called()
        self.assertIn("warning", self._msgs(resp))

    @patch("stripe.checkout.Session.retrieve")
    def test_already_granted_by_webhook_skips_stripe(self, retrieve):
        EditionUnlock.objects.create(
            member=self.member, edition=self.edition, source=EditionUnlock.Source.PAID)
        resp = self._return()
        retrieve.assert_not_called()
        self.assertIn("success", self._msgs(resp))
        self.assertEqual(EditionUnlock.objects.filter(edition=self.edition).count(), 1)

    @patch("stripe.checkout.Session.retrieve")
    def test_replay_is_idempotent(self, retrieve):
        retrieve.return_value = self._session()
        self._return()
        self._return()
        self.assertEqual(EditionUnlock.objects.filter(edition=self.edition).count(), 1)
        self.assertEqual(Transaction.objects.filter(stripe_session_id="cs_test_return").count(), 1)

    def test_anonymous_cannot_use_a_session_id(self):
        with patch("stripe.checkout.Session.retrieve") as retrieve:
            Client().get(f"{self.edition.get_absolute_url()}",
                         {"unlocked": "1", "session_id": "cs_test_return"})
        retrieve.assert_not_called()
        self.assertFalse(EditionUnlock.objects.exists())

    @patch("stripe.checkout.Session.retrieve")
    def test_flowchart_flags_reflect_the_grant_on_next_load(self, retrieve):
        """補發之後同一個使用者重新載入，流程圖功能要是開的。"""
        retrieve.return_value = self._session()
        self._return()
        ctx = self.client_.get(f"{self.edition.get_absolute_url()}flowchart/").context
        self.assertTrue(ctx["can_flowchart_print"])


class LanguagePreservedTests(EditionUnlockTestBase):
    """付款後不能被強行帶回英文版。

    /commerce/ 不在 i18n_patterns 底下（translation/middleware.py 的
    UNPREFIXED_PATHS），購買 view 啟動的語言永遠是英文，get_absolute_url()
    組不出 /zh/ 前綴。所以語言要由表單帶、或看 Referer，且都要過白名單。
    """

    def setUp(self):
        super().setUp()
        self.edition = self.make_edition("lang-test")
        self.client_ = Client()
        self.client_.force_login(self.user)
        self.member = Member.objects.get(pk=self.member.pk)
        self.member.tier_new = self.free_tier
        self.member.save()
        self.url = reverse("commerce:create-edition-unlock-session")

    def _buy(self, extra=None, **headers):
        data = {"edition_id": str(self.edition.id)}
        data.update(extra or {})
        with patch("stripe.checkout.Session.create") as create, \
                self.settings(STRIPE_FLOWCHART_SINGLE_EDITION_PRICE_ID="price_test"):
            create.return_value = type("S", (), {"url": "https://stripe.test/pay"})()
            self.client_.post(self.url, data, **headers)
        return create.call_args.kwargs

    def test_form_lang_zh_keeps_prefix_in_success_and_cancel_urls(self):
        kw = self._buy({"lang": "zh"})
        self.assertIn("/zh/games/", kw["success_url"])
        self.assertIn("/zh/games/", kw["cancel_url"])
        self.assertIn("/?unlocked=1&session_id={CHECKOUT_SESSION_ID}", kw["success_url"])

    def test_every_supported_language_round_trips(self):
        for lang in ("de", "es", "fr", "ja", "zh"):
            self.assertIn(f"/{lang}/games/", self._buy({"lang": lang})["success_url"], lang)

    def test_english_has_no_prefix(self):
        kw = self._buy({"lang": "en"})
        self.assertNotIn("/en/", kw["success_url"])
        self.assertIn("/games/", kw["success_url"])

    def test_referer_is_the_fallback_when_form_has_no_lang(self):
        kw = self._buy(HTTP_REFERER="http://testserver/ja/games/whatever/info/")
        self.assertIn("/ja/games/", kw["success_url"])

    def test_form_lang_wins_over_referer(self):
        kw = self._buy({"lang": "fr"}, HTTP_REFERER="http://testserver/ja/games/x/")
        self.assertIn("/fr/games/", kw["success_url"])

    def test_unsupported_lang_is_ignored_not_trusted(self):
        for bad in ("xx", "../admin", "zh/../../x", "ZH", ""):
            kw = self._buy({"lang": bad})
            self.assertNotIn("admin", kw["success_url"], bad)
            self.assertNotIn("/xx/", kw["success_url"], bad)
            self.assertIn("/games/", kw["success_url"], bad)

    def test_guard_redirects_also_keep_language(self):
        """沒流程圖被擋時導回的頁面也要是使用者的語言。"""
        nochart = self.make_edition("nochart", with_flowchart=False)
        with patch("stripe.checkout.Session.create") as create:
            resp = self.client_.post(self.url, {"edition_id": str(nochart.id), "lang": "zh"})
        create.assert_not_called()
        self.assertTrue(resp["Location"].startswith("/zh/games/"), resp["Location"])

    def test_buy_forms_on_the_page_carry_the_page_language(self):
        EditionUnlock  # noqa: F401  (imported at module top)
        for i in range(3):
            EditionUnlock.objects.create(member=self.member, edition=self.make_edition(f"u{i}"))
        html = self.client_.get(f"/zh{self.edition.get_absolute_url()}").content.decode()
        self.assertIn('name="lang" value="zh"', html)

    def test_free_pick_redirect_keeps_language(self):
        """免費名額那條路在 i18n_patterns 底下，應該本來就對——驗證而不是假設。"""
        resp = self.client_.post(f"/zh{reverse('account:unlock-pick')}",
                                 {"edition_id": str(self.edition.id)})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith("/zh/games/"), resp["Location"])


class SubscriptionLanguageTests(EditionUnlockTestBase):
    """訂閱購買／取消／恢復同樣在 /commerce/ 底下，一樣會被帶回英文版。"""

    def setUp(self):
        super().setUp()
        self.client_ = Client()
        self.client_.force_login(self.user)
        self.member = Member.objects.get(pk=self.member.pk)
        self.member.tier_new = self.free_tier
        self.member.save()

    def _subscribe(self, data=None, **headers):
        with patch("stripe.checkout.Session.create") as create:
            create.return_value = type("S", (), {"url": "https://stripe.test/pay"})()
            self.client_.post(reverse("commerce:create-checkout-session"), data or {}, **headers)
        return create.call_args.kwargs

    def test_success_and_cancel_urls_keep_language(self):
        kw = self._subscribe({"lang": "zh"})
        self.assertIn("/zh/?session_id={CHECKOUT_SESSION_ID}", kw["success_url"])
        self.assertIn("/zh/", kw["cancel_url"])
        self.assertTrue(kw["cancel_url"].rstrip("/").endswith("membership"), kw["cancel_url"])

    def test_english_success_url_is_the_bare_root(self):
        kw = self._subscribe({"lang": "en"})
        self.assertRegex(kw["success_url"], r"^http://testserver/\?session_id=")

    def test_referer_fallback(self):
        kw = self._subscribe(HTTP_REFERER="http://testserver/de/membership/")
        self.assertIn("/de/?session_id=", kw["success_url"])

    def test_cancel_and_resume_redirect_into_the_users_language(self):
        for name in ("commerce:cancel-subscription", "commerce:resume-subscription"):
            resp = self.client_.post(reverse(name), {"lang": "ja"})
            self.assertEqual(resp.status_code, 302, name)
            self.assertTrue(resp["Location"].startswith("/ja/"), (name, resp["Location"]))

    def test_stripe_locale_follows_the_page_language(self):
        expected = {"en": "en", "zh": "zh-TW", "ja": "ja", "de": "de", "fr": "fr", "es": "es"}
        for lang, locale in expected.items():
            self.assertEqual(self._subscribe({"lang": lang})["locale"], locale, lang)

    def test_every_site_language_has_a_stripe_locale(self):
        """新增站上語言卻忘了補對照，會悄悄退回 'auto'。這個測試讓它變成吵的失敗。"""
        from commerce.views import STRIPE_LOCALES
        from django.conf import settings
        missing = {code for code, _ in settings.LANGUAGES} - set(STRIPE_LOCALES)
        self.assertFalse(missing, f"STRIPE_LOCALES 缺少: {missing}")

    def test_unknown_language_falls_back_to_auto_not_an_invalid_locale(self):
        self.assertEqual(self._subscribe({"lang": "xx"})["locale"], "en")  # whitelist -> default
