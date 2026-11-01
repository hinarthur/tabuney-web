"""Beta 模式（settings.BETA_MODE）：付費閘門全開、付費入口關閉、未登入 Rulesbot 每日限量。

基底沿用 test_edition_unlock 的 fixture：free tier 什麼都沒開、prompt_per_week=5，
所以只要 beta 一開還看得到東西，就是 beta 開關放行的，不是 tier 給的。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

from game.models import ChatSession, RulebookScript
from game.rag.constants import ANON_CHAT_PER_DAY
from game.rag.rag_service import QAResult
from game.views.chat_views import get_chat_limits

from .test_edition_unlock import EditionUnlockTestBase

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(BETA_MODE=True, CACHES=LOCMEM)
class BetaOpenAccessTests(EditionUnlockTestBase):
    def test_anonymous_sees_non_initial_flowchart_and_tools(self):
        edition = self.make_edition("variant", initial=False)
        ctx = Client().get(f"{edition.get_absolute_url()}flowchart/").context
        self.assertFalse(ctx["flowchart_charts"][0]["locked"])
        self.assertEqual(len(ctx["flowchart_viewer_configs"]), 1)
        self.assertTrue(ctx["can_flowchart_fullscreen"])
        self.assertTrue(ctx["can_flowchart_print"])
        self.assertTrue(ctx["can_flowchart_tour"])

    def test_anonymous_sees_full_script(self):
        edition = self.make_edition("scripted")
        RulebookScript.objects.create(
            rulebook=edition.rulebooks.first(), edition=edition, ruleset="basic",
            language=self.tribe, title="T", script_text="one\ntwo\nthree\nfour",
            is_published=True,
        )
        ctx = Client().get(f"{edition.get_absolute_url()}script/").context
        self.assertNotIn("locked", ctx["script_data"])
        self.assertEqual(ctx["script_data"]["text"], "one\ntwo\nthree\nfour")

    def test_logged_in_chat_is_unlimited(self):
        edition = self.make_edition("chatty")
        self.assertEqual(get_chat_limits(self.user, edition.id)["total"], -1)

    def test_edition_page_has_no_paid_ui(self):
        edition = self.make_edition("plain", initial=False)
        client = Client()
        client.force_login(self.user)
        for tab in ("", "flowchart/"):
            html = client.get(f"{edition.get_absolute_url()}{tab}").content.decode()
            self.assertNotIn(reverse("account:membership"), html)
            # 只看元素本身（JS 裡留著的 '.edition-access-cta-*' selector 無害）
            self.assertNotIn('class="edition-access-cta', html)
            self.assertNotIn('id="edition-access-modal"', html)

    def test_paid_entry_points_redirect_home(self):
        edition = self.make_edition("buyable")
        client = Client()
        client.force_login(self.user)
        home = reverse("home")
        with patch("stripe.checkout.Session.create") as mock_create:
            for url in (
                reverse("account:membership"),
                reverse("commerce:create-checkout-session"),
                reverse("commerce:create-edition-unlock-session"),
                reverse("account:unlock-pick"),
            ):
                resp = client.post(url, {"edition_id": str(edition.id)})
                self.assertRedirects(resp, home, fetch_redirect_response=False, msg_prefix=url)
            mock_create.assert_not_called()


@override_settings(BETA_MODE=True, CACHES=LOCMEM)
class BetaAnonymousChatTests(EditionUnlockTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.edition = self.make_edition("chat")
        self.url = f"/api/game/editions/{self.edition.id}/chat/"
        bundle = SimpleNamespace(rulebooks=[self.edition.rulebooks.first()], status="ready")
        patcher = patch("game.views.chat_views.resolve_chat_bundle", return_value=bundle)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.rag = MagicMock()
        self.rag.classify_question.return_value = "other"
        self.rag.answer_question_whole.return_value = QAResult(answer="A", model="Gemini")
        patcher = patch("game.views.chat_views.get_rag_service", return_value=self.rag)
        patcher.start()
        self.addCleanup(patcher.stop)

    def ask(self, client, session_id=None):
        return client.post(
            self.url, {"message": "q", "session_id": session_id}, content_type="application/json",
        )

    def test_daily_quota_then_429(self):
        client = Client()
        for i in range(ANON_CHAT_PER_DAY):
            resp = self.ask(client)
            self.assertEqual(resp.status_code, 200, i)
            self.assertEqual(resp.json()["limits"]["remaining"], ANON_CHAT_PER_DAY - i - 1)
        resp = self.ask(client)
        self.assertEqual(resp.status_code, 429)
        self.assertTrue(resp.json()["login_required"])

    def test_provider_failure_does_not_consume_quota(self):
        self.rag.answer_question_whole.side_effect = RuntimeError("down")
        self.assertEqual(self.ask(Client()).status_code, 503)
        resp = Client().get(self.url)
        self.assertEqual(resp.json()["limits"]["remaining"], ANON_CHAT_PER_DAY)

    def test_anonymous_session_has_no_user_and_cannot_hijack_member_session(self):
        member_session = ChatSession.objects.create(edition=self.edition, user=self.user)
        resp = self.ask(Client(), session_id=str(member_session.id))
        self.assertEqual(resp.status_code, 200)
        anon_session = ChatSession.objects.get(pk=resp.json()["session_id"])
        self.assertNotEqual(anon_session.pk, member_session.pk)
        self.assertIsNone(anon_session.user_id)
        self.assertEqual(member_session.messages.count(), 0)

    def test_anonymous_get_returns_no_history(self):
        data = Client().get(self.url).json()
        self.assertEqual(data["messages"], [])
        self.assertEqual(data["limits"]["total"], ANON_CHAT_PER_DAY)

    def test_logged_in_user_is_not_counted_against_anon_quota(self):
        client = Client()
        client.force_login(self.user)
        for _ in range(ANON_CHAT_PER_DAY + 1):
            self.assertEqual(self.ask(client).status_code, 200)


@override_settings(BETA_MODE=False, CACHES=LOCMEM)
class BetaOffKeepsPaywallTests(EditionUnlockTestBase):
    def test_anonymous_chat_still_requires_login(self):
        edition = self.make_edition("chat")
        resp = Client().post(
            f"/api/game/editions/{edition.id}/chat/", {"message": "q"},
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (401, 403))

    def test_non_initial_flowchart_still_locked(self):
        edition = self.make_edition("variant", initial=False)
        ctx = Client().get(f"{edition.get_absolute_url()}flowchart/").context
        self.assertTrue(ctx["flowchart_charts"][0]["locked"])
