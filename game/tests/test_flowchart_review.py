"""
流程圖審核發布（game/flowchart_review.py）。

重點：編輯者改不到公開內容、公開頁只讀 reviewer 核准的快照、核准綁定內容雜湊。
"""

import json

from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from game import flowchart_review as fr
from game.models import (
    Edition, FlowchartPublication, FlowchartReview, Game, Rulebook, RulebookFlowchart,
)
from game.selectors import editions_with_published_flowchart
from translation.models import Tribe


def _flow(label):
    return {
        "nodes": [
            {"id": "p1", "type": "group", "data": {"label": "Setup"}},
            {"id": "n1", "type": "action", "data": {"label": label, "phase_id": "p1"}},
        ],
        "edges": [],
    }


def _user(username, *codenames, staff=True):
    user = User.objects.create_user(username=username, password="pw", is_staff=staff)
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="game", codename__in=codenames,
        ))
    return User.objects.get(pk=user.pk)   # 重新取一份，避免權限快取


EDITOR_PERMS = ("view_rulebookflowchart", "change_rulebookflowchart", "view_flowchartreview")
REVIEWER_PERMS = ("view_rulebookflowchart", "review_rulebookflowchart", "view_flowchartreview")


class FlowchartReviewTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tribe, _ = Tribe.objects.get_or_create(pk=1, defaults={"language": "en", "name": "English"})
        cls.editor = _user("editor", *EDITOR_PERMS)
        cls.reviewer = _user("reviewer", *REVIEWER_PERMS)
        cls.viewer = _user("viewer", "view_rulebookflowchart")
        cls.member = _user("member", staff=False)
        cls.game = Game.objects.create(canonical_name="Review Game")
        cls.edition = Edition.objects.create(game=cls.game, name="Review Game", slug="review-game")
        cls.rulebook = Rulebook.objects.create(edition=cls.edition, language=cls.tribe, title="Rules")

    def setUp(self):
        self.chart = RulebookFlowchart.objects.create(
            rulebook=self.rulebook, edition=self.edition, ruleset="basic",
            initial=True, react_flow_json=_flow("Version one"),
        )

    def _approve(self, chart=None):
        chart = chart or self.chart
        chart.refresh_from_db()
        return fr.approve(chart, self.reviewer, chart.content_hash)

    def _public_labels(self):
        resp = self.client.get("/games/review-game/flowchart/")
        if resp.status_code != 200:
            return resp.status_code
        data = resp.context["flowchart_viewer_configs"][0]["reactFlowData"]
        return [n["data"]["label"] for n in data["nodes"] if n.get("type") != "group"]

    def _adjust(self, user, label):
        self.client.force_login(user)
        return self.client.patch(
            f"/api/game/rulebooks/{self.rulebook.id}/flowchart/adjust/?ruleset=basic",
            data=json.dumps({"detail": "detailed", "adjusted_json": _flow(label)}),
            content_type="application/json",
        )


class PermissionTests(FlowchartReviewTestBase):
    def test_editor_cannot_approve_or_unpublish(self):
        with self.assertRaises(PermissionDenied):
            fr.approve(self.chart, self.editor, self.chart.content_hash)
        self._approve()
        with self.assertRaises(PermissionDenied):
            fr.unpublish(self.chart, self.editor)
        self.assertTrue(self.chart.publication.is_live)

    def test_reviewer_can_approve_own_edit_and_it_is_logged(self):
        self.chart.content_edited_by = self.reviewer
        self.chart.save()
        review = self._approve()
        self.assertEqual(review.actor, self.reviewer)
        self.assertEqual(review.last_editor, self.reviewer)

    def test_editor_without_review_perm_gets_403_on_review_page(self):
        self.client.force_login(self.editor)
        url = reverse("admin:game_rulebookflowchart_review", args=[self.chart.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        resp = self.client.post(url, {"decision": "approve", "expected_hash": self.chart.content_hash})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(FlowchartPublication.objects.filter(flowchart=self.chart).exists())

    def test_editor_change_form_has_no_review_link(self):
        self.client.force_login(self.editor)
        resp = self.client.get(reverse("admin:game_rulebookflowchart_change", args=[self.chart.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "前往審核")
        self.assertContains(resp, "送審")

    def test_adjust_api_requires_change_permission(self):
        self.assertEqual(self._adjust(self.viewer, "Hacked").status_code, 403)
        resp = self._adjust(self.editor, "Edited")
        self.assertEqual(resp.status_code, 200)
        self.chart.refresh_from_db()
        self.assertEqual(self.chart.content_edited_by, self.editor)
        self.assertEqual(self.chart.content_hash, self.chart.compute_content_hash())

    def test_draft_api_is_not_open_to_members(self):
        url = f"/api/game/rulebooks/{self.rulebook.id}/flowchart/?ruleset=basic"
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url + "&regenerate=true").status_code, 403)


class PublishFlowTests(FlowchartReviewTestBase):
    def test_unreviewed_chart_is_not_public(self):
        self.assertEqual(self._public_labels(), 404)
        self.assertEqual(fr.review_state(self.chart), fr.State.DRAFT)

    def test_edits_after_approval_keep_public_on_approved_version(self):
        self._approve()
        self.assertEqual(self._public_labels(), ["Version one"])

        self._adjust(self.editor, "Version two")
        self.chart.refresh_from_db()
        self.assertEqual(fr.review_state(self.chart), fr.State.LIVE_WITH_CHANGES)
        self.client.logout()
        self.assertEqual(self._public_labels(), ["Version one"])

        self._approve()
        self.assertEqual(self._public_labels(), ["Version two"])
        self.assertEqual(
            list(self.chart.reviews.values_list("action", flat=True)),
            ["approved", "approved"],
        )

    def test_stale_hash_is_rejected(self):
        seen_hash = self.chart.content_hash
        self._adjust(self.editor, "Changed while reviewing")
        self.chart.refresh_from_db()
        with self.assertRaises(fr.ReviewError):
            fr.approve(self.chart, self.reviewer, seen_hash)
        self.assertFalse(FlowchartPublication.objects.filter(flowchart=self.chart).exists())

    def test_empty_chart_cannot_be_published(self):
        empty = RulebookFlowchart.objects.create(rulebook=self.rulebook, ruleset="empty")
        with self.assertRaises(fr.ReviewError):
            fr.approve(empty, self.reviewer, empty.content_hash)

    def test_submit_then_reject_states(self):
        fr.submit(self.chart, self.editor)
        self.assertEqual(fr.review_state(self.chart), fr.State.PENDING)
        fr.reject(self.chart, self.reviewer, self.chart.content_hash)
        self.assertEqual(fr.review_state(self.chart), fr.State.REJECTED)
        # 改過之後就不再是「被退回的那一版」
        self._adjust(self.editor, "Fixed")
        self.chart.refresh_from_db()
        self.assertEqual(fr.review_state(self.chart), fr.State.DRAFT)

    def test_editor_can_withdraw_pending_submission(self):
        fr.submit(self.chart, self.editor)
        with self.assertRaises(PermissionDenied):
            fr.withdraw(self.chart, self.member)
        fr.withdraw(self.chart, self.editor)
        self.assertEqual(fr.review_state(self.chart), fr.State.DRAFT)
        # 不是待審狀態就不能再收回
        with self.assertRaises(fr.ReviewError):
            fr.withdraw(self.chart, self.editor)
        # 收回後可以重新送審
        fr.submit(self.chart, self.editor)
        self.assertEqual(fr.review_state(self.chart), fr.State.PENDING)

    def test_withdraw_button_only_while_pending(self):
        self.client.force_login(self.editor)
        url = reverse("admin:game_rulebookflowchart_change", args=[self.chart.pk])
        self.assertNotContains(self.client.get(url), "收回送審")
        fr.submit(self.chart, self.editor)
        self.assertContains(self.client.get(url), "收回送審")
        resp = self.client.post(
            reverse("admin:game_rulebookflowchart_withdraw_review", args=[self.chart.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(fr.review_state(RulebookFlowchart.objects.get(pk=self.chart.pk)), fr.State.DRAFT)

    def test_editor_can_restore_draft_to_published(self):
        with self.assertRaises(fr.ReviewError):
            fr.restore_published(self.chart, self.editor)   # 沒有公開版
        self._approve()
        with self.assertRaises(fr.ReviewError):
            fr.restore_published(self.chart, self.editor)   # 草稿與公開版相同
        self._adjust(self.editor, "Messy draft")
        self.chart.refresh_from_db()
        self.assertEqual(fr.review_state(self.chart), fr.State.LIVE_WITH_CHANGES)
        with self.assertRaises(PermissionDenied):
            fr.restore_published(self.chart, self.member)
        fr.restore_published(self.chart, self.editor)
        self.chart.refresh_from_db()
        self.assertEqual(fr.review_state(self.chart), fr.State.LIVE)
        self.assertEqual(self.chart.effective_json, _flow("Version one"))

    def test_restore_button_only_when_draft_differs(self):
        self.client.force_login(self.editor)
        url = reverse("admin:game_rulebookflowchart_change", args=[self.chart.pk])
        self._approve()
        self.assertNotContains(self.client.get(url), "還原為公開版")
        self._adjust(self.editor, "Changed")
        self.client.force_login(self.editor)
        self.assertContains(self.client.get(url), "還原為公開版")

    def test_unpublish_hides_everywhere(self):
        self._approve()
        self.assertEqual(editions_with_published_flowchart([self.edition.id]), {self.edition.id})
        fr.unpublish(self.chart, self.reviewer)
        self.assertEqual(self._public_labels(), 404)
        self.assertEqual(editions_with_published_flowchart([self.edition.id]), set())
        self.assertFalse(RulebookFlowchart.objects.published().exists())

    def test_review_page_approve_via_admin(self):
        self.client.force_login(self.reviewer)
        url = reverse("admin:game_rulebookflowchart_review", args=[self.chart.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        resp = self.client.post(url, {
            "decision": "approve", "expected_hash": self.chart.content_hash, "comment": "OK",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(self.chart.publication.is_live)
        self.assertEqual(self.chart.publication.approved_by_name, "reviewer")

    def test_duplicate_is_a_new_draft(self):
        self._approve()
        admin = User.objects.create_superuser("root", password="pw")
        self.client.force_login(admin)
        self.client.post(reverse("admin:game_rulebookflowchart_changelist"), {
            "action": "duplicate_selected", "_selected_action": [str(self.chart.pk)],
        })
        copy = RulebookFlowchart.objects.exclude(pk=self.chart.pk).get(rulebook=self.rulebook)
        self.assertFalse(FlowchartPublication.objects.filter(flowchart=copy).exists())
        self.assertEqual(copy.content_edited_by, admin)

    def test_review_status_filter(self):
        self.client.force_login(self.reviewer)
        fr.submit(self.chart, self.editor)
        url = reverse("admin:game_rulebookflowchart_changelist")
        resp = self.client.get(url, {"review": "pending"})
        self.assertEqual(list(resp.context["cl"].queryset), [self.chart])
        resp = self.client.get(url, {"review": "live"})
        self.assertEqual(list(resp.context["cl"].queryset), [])


class TranslationAndSyncTests(FlowchartReviewTestBase):
    def test_gc_keeps_texts_used_only_by_live_version(self):
        from game.rag.flowchart.i18n import collect_inuse_hashes, compute_hash

        self._approve()
        self._adjust(self.editor, "Version two")
        hashes = collect_inuse_hashes()
        self.assertIn(compute_hash("Version one"), hashes)
        self.assertIn(compute_hash("Version two"), hashes)

    def test_sync_sends_publication_without_local_user_fk(self):
        from game.sync_service import GameSyncService

        self.chart.content_edited_by = self.editor
        self.chart.save()
        self._approve()
        layers, _, stats = GameSyncService.__new__(GameSyncService)._collect_db_records()
        entries = {e["model"]: e for layer in layers for e in layer}
        self.assertIn("game.flowchartpublication", entries)
        self.assertNotIn("game.flowchartreview", entries)
        chart_fields = entries["game.rulebookflowchart"]["data"][0]["fields"]
        self.assertNotIn("content_edited_by", chart_fields)
        self.assertNotIn("is_published", chart_fields)

    def test_unapproved_chart_is_not_synced(self):
        from game.sync_service import GameSyncService

        layers, _, _ = GameSyncService.__new__(GameSyncService)._collect_db_records()
        models = {e["model"] for layer in layers for e in layer}
        self.assertNotIn("game.rulebookflowchart", models)

    def test_withdrawn_publication_is_sent_in_delta(self):
        from django.utils import timezone
        from game.sync_service import GameSyncService

        self._approve()
        since = timezone.now()
        fr.unpublish(self.chart, self.reviewer)
        layers, _, _ = GameSyncService.__new__(GameSyncService)._collect_db_records(since=since)
        pubs = [e for layer in layers for e in layer if e["model"] == "game.flowchartpublication"]
        self.assertEqual(len(pubs), 1)
        self.assertFalse(pubs[0]["data"][0]["fields"]["is_live"])


class DraftPreviewTests(FlowchartReviewTestBase):
    """公開流程圖頁的發布前草稿預覽：?preview=<flowchart_id>，限具備 view 權限的人。"""

    URL = "/games/review-game/flowchart/"

    def _labels(self, resp):
        data = resp.context["flowchart_viewer_configs"][0]["reactFlowData"]
        return [n["data"]["label"] for n in data["nodes"] if n.get("type") != "group"]

    def _get(self, user, url=None, chart=None):
        if user is None:
            self.client.logout()
        else:
            self.client.force_login(user)
        chart = chart or self.chart
        return self.client.get(f"{url or self.URL}?preview={chart.pk}")

    def test_staff_sees_draft_instead_of_published(self):
        self._approve()
        self._adjust(self.editor, "Draft version")

        resp = self._get(self.viewer)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._labels(resp), ["Draft version"])
        self.assertContains(resp, "草稿預覽")
        self.assertEqual(resp["X-Robots-Tag"], "noindex, nofollow")
        self.assertIn("no-store", resp["Cache-Control"])
        self.assertContains(resp, '<meta name="robots" content="noindex, nofollow">', html=False)

    def test_param_is_ignored_for_members_and_anonymous(self):
        self._approve()
        self._adjust(self.editor, "Draft version")

        for user in (self.member, None):
            resp = self._get(user)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self._labels(resp), ["Version one"])
            self.assertNotContains(resp, "草稿預覽")
            self.assertFalse(resp.has_header("X-Robots-Tag"))

    def test_unpublished_paywalled_chart_can_be_previewed(self):
        self.chart.initial = False
        self.chart.save()
        self.assertFalse(RulebookFlowchart.objects.published().exists())

        resp = self._get(self.viewer)

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["flowchart_charts"][0]["locked"])
        self.assertEqual(self._labels(resp), ["Version one"])
        # 同一網址不帶權限仍是 404（沒有任何已發布的圖）
        self.assertEqual(self._get(self.member).status_code, 404)

    def test_chart_from_another_edition_is_ignored(self):
        other_edition = Edition.objects.create(game=self.game, name="Other", slug="other-ed")
        other_rb = Rulebook.objects.create(edition=other_edition, language=self.tribe)
        other = RulebookFlowchart.objects.create(
            rulebook=other_rb, ruleset="basic", react_flow_json=_flow("Elsewhere"),
        )
        self._approve()

        resp = self._get(self.viewer, chart=other)

        self.assertEqual(self._labels(resp), ["Version one"])
        self.assertNotContains(resp, "草稿預覽")

    def test_localized_preview_and_missing_translation_count(self):
        from game.models import FlowchartTextTranslation
        from game.rag.flowchart.i18n import compute_hash

        FlowchartTextTranslation.objects.create(
            text_hash=compute_hash("Version one"), source_text="Version one", source_lang="en",
            translations={"en": "Version one", "ja": "バージョン1"},
        )

        resp = self._get(self.viewer, url="/ja" + self.URL)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._labels(resp), ["バージョン1"])
        preview = resp.context["flowchart_preview"]
        self.assertEqual(preview["current_lang"], "ja")
        self.assertEqual(preview["missing"], 1)   # 群組標題 "Setup" 沒有日文
        # 語言按鈕保留 ?preview=，前綴正確
        urls = {code: url for code, _label, url in preview["langs"]}
        self.assertEqual(urls["en"], f"{self.URL}?preview={self.chart.pk}")
        self.assertEqual(urls["de"], f"/de{self.URL}?preview={self.chart.pk}")

    def test_admin_pages_link_to_all_language_previews(self):
        from django.conf import settings

        expected = f"/fr{self.URL}?preview={self.chart.pk}"
        self.client.force_login(self.editor)
        change = self.client.get(reverse("admin:game_rulebookflowchart_change", args=[self.chart.pk]))
        self.assertContains(change, expected)
        self.assertEqual(len(change.context["preview_urls"]), len(settings.LANGUAGES))

        self.client.force_login(self.reviewer)
        review = self.client.get(reverse("admin:game_rulebookflowchart_review", args=[self.chart.pk]))
        self.assertContains(review, expected)
