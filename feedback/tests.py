"""
回饋功能：流程圖建議（含導覽節點）開放匿名、問卷 API。

匿名零 cookie 是這裡最容易被不小心破壞的性質（渲染一個 {% csrf_token %}、
在 /api/ 帶 ?lang= 都會讓瀏覽器拿到 cookie），所以每條匿名路徑都檢查 response.cookies。
"""

import json
from unittest import mock

from django.core.cache import cache
from django.db.models import ProtectedError
from django.test import Client, override_settings
from django.urls import reverse

from feedback.models import Survey, SurveyAnswer, SurveyChoice, SurveyQuestion, SurveyResponse
from game.models import FlowchartSuggestion, RulebookFlowchart
from feedback import security
from member.test_edition_unlock import EditionUnlockTestBase

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CSRF = "a" * 32


def _post(client, url, payload, **extra):
    return client.post(url, json.dumps(payload), content_type="application/json", **extra)


@override_settings(CACHES=LOCMEM)
class FlowchartSuggestionAnonymousTests(EditionUnlockTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.edition = self.make_edition("charted")
        self.chart = RulebookFlowchart.objects.get(rulebook__edition=self.edition)
        self.url = reverse("games:suggest-flowchart")
        self.payload = {
            "flowchart_id": str(self.chart.id),
            "edition_id": str(self.edition.id),
            "content": "This step is missing the draw.",
            "node_id": "n3",
            "node_label": "Draw two cards",
        }

    @override_settings(BETA_MODE=True)
    def test_anonymous_can_send_node_feedback_in_beta_without_cookies(self):
        resp = _post(Client(), self.url, self.payload)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(dict(resp.cookies), {})
        s = FlowchartSuggestion.objects.get()
        self.assertIsNone(s.submitted_by)
        self.assertEqual((s.node_id, s.node_label), ("n3", "Draw two cards"))

    @override_settings(BETA_MODE=False)
    def test_anonymous_is_rejected_outside_beta(self):
        resp = _post(Client(), self.url, self.payload)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(FlowchartSuggestion.objects.exists())

    @override_settings(BETA_MODE=True)
    def test_honeypot_pretends_success_but_stores_nothing(self):
        resp = _post(Client(), self.url, {**self.payload, "website": "http://spam"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(FlowchartSuggestion.objects.exists())

    def test_signed_in_request_still_needs_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(_post(client, self.url, self.payload).status_code, 403)

        client.cookies["csrftoken"] = CSRF
        resp = _post(client, self.url, self.payload, HTTP_X_CSRFTOKEN=CSRF)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(FlowchartSuggestion.objects.get().submitted_by, self.member)


@override_settings(CACHES=LOCMEM, BETA_MODE=True)
class SurveyApiTests(EditionUnlockTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        # 測試不想等 3 秒；最短填寫時間另有專門的測試
        patcher = mock.patch.object(security, "MIN_FILL_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.edition = self.make_edition("surveyed", with_flowchart=False)
        self.survey = Survey.objects.create(
            kind=Survey.Kind.EDITION, name="v1", is_active=True,
            title={"en": "Quick survey", "zh": "小問卷"},
        )
        self.q_single = SurveyQuestion.objects.create(
            survey=self.survey, order=1, qtype="single", required=True,
            text={"en": "Was it clear?", "zh": "清楚嗎？"},
        )
        self.yes = SurveyChoice.objects.create(question=self.q_single, order=1, text={"en": "Yes"})
        self.no = SurveyChoice.objects.create(question=self.q_single, order=2, text={"en": "No"})
        self.q_multi = SurveyQuestion.objects.create(
            survey=self.survey, order=2, qtype="multi", text={"en": "What did you use?"},
        )
        self.m = [
            SurveyChoice.objects.create(question=self.q_multi, order=i, text={"en": f"C{i}"})
            for i in range(3)
        ]
        self.q_text = SurveyQuestion.objects.create(
            survey=self.survey, order=3, qtype="text", text={"en": "Anything else?"},
        )

        self.get_url = reverse("feedback:survey", args=["edition"])
        self.post_url = reverse("feedback:survey-respond", args=[self.survey.id])

    def answers(self, **overrides):
        base = {
            str(self.q_single.id): self.yes.id,
            str(self.q_multi.id): [self.m[0].id, self.m[2].id],
            str(self.q_text.id): "Loved the tour",
        }
        base.update(overrides)
        return {"edition_id": str(self.edition.id), "page": "flowchart", "lang": "en", "answers": base,
                "token": security.issue_token(self.survey.id)}

    # ── GET ──

    def test_get_returns_localized_questions_without_cookies(self):
        resp = Client().get(self.get_url, {"edition": str(self.edition.id), "l": "zh"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(dict(resp.cookies), {})
        data = resp.json()
        self.assertTrue(data["token"])
        self.assertEqual(data["survey"]["title"], "小問卷")
        texts = [q["text"] for q in data["survey"]["questions"]]
        # 缺中文的題目退回英文
        self.assertEqual(texts, ["清楚嗎？", "What did you use?", "Anything else?"])

    def test_get_without_active_survey_is_204(self):
        self.survey.is_active = False
        self.survey.save()
        resp = Client().get(self.get_url, {"edition": str(self.edition.id)})
        self.assertEqual(resp.status_code, 204)

    def test_edition_survey_requires_edition(self):
        self.assertEqual(Client().get(self.get_url).status_code, 400)

    @override_settings(BETA_MODE=False)
    def test_site_survey_closes_outside_beta(self):
        Survey.objects.create(kind=Survey.Kind.SITE, name="beta", is_active=True)
        SurveyQuestion.objects.create(
            survey=Survey.objects.get(kind="site"), qtype="text", text={"en": "Hi?"},
        )
        resp = Client().get(reverse("feedback:survey", args=["site"]))
        self.assertEqual(resp.status_code, 204)

    # ── POST ──

    def test_anonymous_response_is_stored_without_identity_or_cookies(self):
        resp = _post(Client(), self.post_url, self.answers())
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(dict(resp.cookies), {})
        r = SurveyResponse.objects.get()
        self.assertIsNone(r.member)
        self.assertEqual((r.edition, r.edition_name, r.page), (self.edition, "surveyed", "flowchart"))
        # 單選 1 列 + 複選 2 列 + 文字 1 列
        self.assertEqual(r.answers.count(), 4)
        self.assertEqual(
            set(r.answers.exclude(choice=None).values_list("choice_id", flat=True)),
            {self.yes.id, self.m[0].id, self.m[2].id},
        )

    def test_missing_required_answer_is_rejected(self):
        payload = self.answers()
        del payload["answers"][str(self.q_single.id)]
        resp = _post(Client(), self.post_url, payload)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["errors"], {str(self.q_single.id): "required"})
        self.assertFalse(SurveyResponse.objects.exists())

    def test_other_choice_stores_its_text(self):
        self.m[2].is_other = True
        self.m[2].save()
        payload = self.answers()
        payload["others"] = {str(self.m[2].id): "  my own tool  ", str(self.m[0].id): "ignored"}
        resp = _post(Client(), self.post_url, payload)
        self.assertEqual(resp.status_code, 200, resp.content)
        r = SurveyResponse.objects.get()
        self.assertEqual(r.answers.get(choice=self.m[2]).text, "my own tool")
        self.assertEqual(r.answers.get(choice=self.m[0]).text, "")
        data = Client().get(self.get_url, {"edition": str(self.edition.id)}).json()
        flags = [c["other"] for q in data["survey"]["questions"] for c in q["choices"]]
        self.assertEqual(flags.count(True), 1)

    def test_partial_response_allows_missing_required_answers(self):
        payload = self.answers()
        del payload["answers"][str(self.q_single.id)]
        payload["partial"] = True
        resp = _post(Client(), self.post_url, payload)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(SurveyResponse.objects.get().is_partial)

    def test_partial_response_still_validates_choices_and_rejects_empty(self):
        resp = _post(Client(), self.post_url, self.answers(**{str(self.q_single.id): self.m[0].id}) | {"partial": True})
        self.assertEqual(resp.status_code, 400)
        resp = _post(Client(), self.post_url, {"edition_id": str(self.edition.id), "answers": {}, "partial": True,
                          "token": security.issue_token(self.survey.id)})
        self.assertEqual(resp.status_code, 400)

    def test_choice_from_another_question_is_rejected(self):
        resp = _post(Client(), self.post_url, self.answers(**{str(self.q_single.id): self.m[0].id}))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["errors"], {str(self.q_single.id): "invalid_choice"})

    def test_single_choice_question_rejects_multiple_picks(self):
        resp = _post(Client(), self.post_url,
                     self.answers(**{str(self.q_single.id): [self.yes.id, self.no.id]}))
        self.assertEqual(resp.status_code, 400)

    def test_member_can_answer_again(self):
        # 不記「填過」：半途關掉的人要能再填
        client = Client()
        client.force_login(self.user)
        self.assertEqual(_post(client, self.post_url, self.answers()).status_code, 200)
        again = self.answers(**{str(self.q_text.id): "A second thought"})
        self.assertEqual(_post(client, self.post_url, again).status_code, 200)
        self.assertEqual(SurveyResponse.objects.exclude(member=None).count(), 2)

    # ── 防機器人 ──

    def test_missing_or_forged_token_is_silently_dropped(self):
        for token in (None, "", "garbage", security.issue_token(self.survey.id + 999)):
            payload = self.answers()
            payload["token"] = token
            resp = _post(Client(), self.post_url, payload)
            self.assertEqual(resp.status_code, 200)
        self.assertFalse(SurveyResponse.objects.exists())

    def test_submitting_faster_than_a_human_is_silently_dropped(self):
        with mock.patch.object(security, "MIN_FILL_SECONDS", 60):
            resp = _post(Client(), self.post_url, self.answers())
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SurveyResponse.objects.exists())

    def test_expired_token_asks_for_refresh(self):
        with mock.patch.object(security, "TOKEN_MAX_AGE", -1):
            resp = _post(Client(), self.post_url, self.answers())
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "expired")

    def test_one_token_cannot_be_reused_forever(self):
        payload = self.answers()
        codes = []
        for i in range(security.TOKEN_MAX_USES + 1):
            payload["answers"][str(self.q_text.id)] = f"msg {i}"
            codes.append(_post(Client(), self.post_url, payload).status_code)
        self.assertEqual(codes[-1], 429)
        self.assertEqual(SurveyResponse.objects.count(), security.TOKEN_MAX_USES)

    def test_identical_content_is_stored_once(self):
        self.assertEqual(_post(Client(), self.post_url, self.answers()).status_code, 200)
        self.assertEqual(_post(Client(), self.post_url, self.answers()).status_code, 200)
        self.assertEqual(SurveyResponse.objects.count(), 1)

    def test_member_hourly_limit(self):
        client = Client()
        client.force_login(self.user)
        with mock.patch.object(security, "TOKEN_MAX_USES", 100):
            codes = [
                _post(client, self.post_url,
                      self.answers(**{str(self.q_text.id): f"m{i}"})).status_code
                for i in range(security.MEMBER_SUBMISSIONS_PER_HOUR + 1)
            ]
        self.assertEqual(codes[-1], 429)

    def test_signed_in_post_needs_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(_post(client, self.post_url, self.answers()).status_code, 403)

    def test_inactive_survey_is_closed(self):
        self.survey.is_active = False
        self.survey.save()
        self.assertEqual(_post(Client(), self.post_url, self.answers()).status_code, 410)

    def test_answered_questions_and_choices_cannot_be_deleted(self):
        _post(Client(), self.post_url, self.answers())
        with self.assertRaises(ProtectedError):
            self.q_single.delete()
        with self.assertRaises(ProtectedError):
            self.yes.delete()
        with self.assertRaises(ProtectedError):
            self.survey.delete()
        self.assertEqual(SurveyAnswer.objects.count(), 4)

    def test_question_edits_invalidate_cached_payload(self):
        params = {"edition": str(self.edition.id), "l": "en"}
        Client().get(self.get_url, params)  # 暖快取
        self.q_text.text = {"en": "Changed?"}
        self.q_text.save()
        texts = [q["text"] for q in Client().get(self.get_url, params).json()["survey"]["questions"]]
        self.assertIn("Changed?", texts)
