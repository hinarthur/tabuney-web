"""版本輸入佇列：批量新增 → 版本輸入頁送審（不寫入）→ 設 approved 才寫入。"""
import hashlib

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from game.models import Edition, EditionImportQueue, Game
from translation.models import Tribe

Q = EditionImportQueue.Status

TEXT = """[game]
name: Azul
[edition]
name: 英文版
language: en
release_year: 2017
"""

BAD_TEXT = """[game]
name: Azul
[edition]
name: 英文版
language: xx
release_year: 2017
"""


def digest(text):
    return hashlib.sha256(text.replace("\r", "").strip().encode("utf-8")).hexdigest()


class EditionImportQueueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Tribe.objects.create(pk=1, name="en - English", language="en")   # Member.tribe 預設 1
        cls.admin = User.objects.create_superuser(username="boss", password="pw", email="b@x.com")

    def setUp(self):
        self.client.force_login(self.admin)

    def test_batch_add_dedupes(self):
        EditionImportQueue.objects.create(name="Catan")
        self.client.post(reverse("admin:game_editionimportqueue_batch_add"),
                         {"names": "catan\n\n  Azul  \nazul\nCarcassonne\n"})
        names = sorted(EditionImportQueue.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Azul", "Carcassonne", "Catan"])
        self.assertTrue(all(s == Q.SEARCHING for s in EditionImportQueue.objects.values_list("status", flat=True)))

    def test_submit_requires_queue_item(self):
        self.client.post(reverse("admin:game_edition_import"),
                         {"text": TEXT, "action": "commit", "preview_hash": digest(TEXT)})
        self.assertFalse(Game.objects.exists())

    def test_submit_saves_text_without_writing(self):
        item = EditionImportQueue.objects.create(name="Azul")
        self.client.post(reverse("admin:game_edition_import"), {
            "text": TEXT, "action": "commit", "preview_hash": digest(TEXT), "queue_id": str(item.pk),
        })
        item.refresh_from_db()
        self.assertEqual(item.status, Q.REVIEW)
        self.assertEqual(item.import_text, TEXT)
        self.assertFalse(Game.objects.exists())

    def _approve(self, item):
        url = reverse("admin:game_editionimportqueue_change", args=[item.pk])
        return self.client.post(url, {"name": item.name, "status": Q.APPROVED, "import_text": item.import_text})

    def test_approve_writes(self):
        item = EditionImportQueue.objects.create(name="Azul", status=Q.REVIEW, import_text=TEXT)
        self._approve(item)
        item.refresh_from_db()
        self.assertEqual(item.status, Q.APPROVED)
        self.assertIsNotNone(item.reviewed_at)
        self.assertTrue(Edition.objects.filter(game__canonical_name="Azul", release_year=2017).exists())

    def test_approve_blocked_on_errors(self):
        item = EditionImportQueue.objects.create(name="Azul", status=Q.REVIEW, import_text=BAD_TEXT)
        resp = self._approve(item)
        self.assertEqual(resp.status_code, 200)   # form 重新顯示錯誤
        item.refresh_from_db()
        self.assertEqual(item.status, Q.REVIEW)
        self.assertFalse(Game.objects.exists())

    def test_approve_from_changelist(self):
        item = EditionImportQueue.objects.create(name="Azul", status=Q.REVIEW, import_text=TEXT)
        self.client.post(reverse("admin:game_editionimportqueue_changelist"), {
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "1",
            "form-0-id": str(item.pk), "form-0-status": Q.APPROVED, "_save": "Save",
        })
        item.refresh_from_db()
        self.assertEqual(item.status, Q.APPROVED)
        self.assertTrue(Game.objects.filter(canonical_name="Azul").exists())

    def test_batch_add_asks_when_game_exists(self):
        Game.objects.create(canonical_name="Azul")
        url = reverse("admin:game_editionimportqueue_batch_add")
        resp = self.client.post(url, {"names": "azul\nCatan"})
        self.assertEqual(resp.status_code, 200)   # 停下來詢問，什麼都還沒建
        self.assertEqual(len(resp.context["conflicts"]), 1)
        self.assertFalse(EditionImportQueue.objects.exists())

        # 選略過
        self.client.post(url, {"names": "azul\nCatan", "orig_1": "azul", "choice_1": "skip", "rename_1": "azul"})
        self.assertEqual(list(EditionImportQueue.objects.values_list("name", flat=True)), ["Catan"])

    def test_batch_add_rename_on_conflict(self):
        Game.objects.create(canonical_name="Azul")
        url = reverse("admin:game_editionimportqueue_batch_add")
        self.client.post(url, {"names": "Azul", "orig_1": "Azul", "choice_1": "rename", "rename_1": "Azul (2017)"})
        self.assertEqual(list(EditionImportQueue.objects.values_list("name", flat=True)), ["Azul (2017)"])

        # 改名後仍撞名 → 再問一次
        resp = self.client.post(url, {"names": "Azul", "orig_1": "Azul", "choice_1": "rename", "rename_1": "azul"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["conflicts"][0]["renamed"])

    def test_hunter_can_submit_but_not_approve(self):
        from django.contrib.auth.models import Permission
        hunter = User.objects.create_user(username="hunter", password="pw", is_staff=True)
        hunter.user_permissions.add(*Permission.objects.filter(
            codename__in=["import_edition", "view_editionimportqueue", "change_editionimportqueue"]))
        self.client.force_login(hunter)
        item = EditionImportQueue.objects.create(name="Azul")
        self.client.post(reverse("admin:game_edition_import"), {
            "text": TEXT, "action": "commit", "preview_hash": digest(TEXT), "queue_id": str(item.pk),
        })
        item.refresh_from_db()
        self.assertEqual(item.status, Q.REVIEW)

        url = reverse("admin:game_editionimportqueue_change", args=[item.pk])
        self.client.post(url, {"name": "Azul", "status": Q.APPROVED, "import_text": TEXT})
        item.refresh_from_db()
        self.assertEqual(item.status, Q.REVIEW)
        self.assertFalse(Game.objects.exists())

    def test_change_page_buttons(self):
        url = reverse("admin:game_editionimportqueue_change", args=[
            EditionImportQueue.objects.create(name="Azul", status=Q.REVIEW, import_text=TEXT).pk])
        item = EditionImportQueue.objects.get(name="Azul")
        resp = self.client.get(url)
        self.assertContains(resp, 'name="_approve"')
        self.assertContains(resp, 'name="_skip"')

        # skip：直接設成 skip，不寫入
        self.client.post(url, {"name": "Azul", "status": Q.REVIEW, "import_text": TEXT, "_skip": "skip"})
        item.refresh_from_db()
        self.assertEqual(item.status, Q.SKIP)
        self.assertFalse(Game.objects.exists())

        # 寫入DB：表單上 status 寫什麼都以按鈕為準
        self.client.post(url, {"name": "Azul", "status": Q.SKIP, "import_text": TEXT, "_approve": "x"})
        item.refresh_from_db()
        self.assertEqual(item.status, Q.APPROVED)
        self.assertTrue(Game.objects.filter(canonical_name="Azul").exists())
        self.assertNotContains(self.client.get(url), 'name="_approve"')
