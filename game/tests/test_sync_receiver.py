"""
sync_views.sync_game_data：VPS 端收資料時的 upsert 行為。

重點是「natural key 撞到、但 PK 不同」這一類：內容重新產生時 PK 會換新，
VPS 上的舊 row 還在，pk-based 的 exists 檢查看不到它，直接 INSERT 就撞
unique constraint（實際發生過：uq_flowchart_rulebook_ruleset）。
"""
import json
import uuid

from django.contrib.auth import get_user_model
from django.core import serializers as django_serializers
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from game.models import (
    Edition,
    FlowchartSuggestion,
    FlowchartTextTranslation,
    Game,
    Rulebook,
    RulebookFlowchart,
    RulebookScript,
)
from translation.models import Tribe


def _payload(objs, model_label="game.rulebookflowchart", sync_type="delta"):
    return {
        "sync_type": sync_type,
        "layers": [[{
            "model": model_label,
            "count": len(objs),
            "data": json.loads(django_serializers.serialize("json", objs)),
        }]],
    }


class SyncFlowchartUpsertTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Member.tribe 的 default=1 指向 migration 種下的那筆 Tribe。整包測試一起跑時
        # 那筆可能已經不在（例：TransactionTestCase 收尾會 truncate 掉 migration 資料），
        # 所以這裡自己確保 pk=1 存在，再建使用者。
        cls.tribe, _ = Tribe.objects.get_or_create(
            pk=1, defaults={"name": "Sync test tribe", "language": None},
        )
        cls.user = get_user_model().objects.create_user(
            username="syncbot", email="syncbot@example.com", password="x",
        )
        cls.game = Game.objects.create(canonical_name="Catan")
        cls.edition = Edition.objects.create(game=cls.game, name="Catan", slug="catan-test")
        cls.rulebook = Rulebook.objects.create(edition=cls.edition, language=cls.tribe)

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("sync-game-data")

    def _post(self, payload):
        return self.client.post(self.url, data=payload, content_type="application/json")

    def _incoming(self, ruleset="First time playing", **kwargs):
        """模擬「本地重新產生、換了新 PK」的那一筆（尚未存進這個 DB）。"""
        now = timezone.now()
        return RulebookFlowchart(
            id=uuid.uuid4(), rulebook=self.rulebook, edition=self.edition,
            ruleset=ruleset, detail="detailed",
            created_at=now, updated_at=now, **kwargs,
        )

    def _chart(self, ruleset="First time playing", **kwargs):
        return RulebookFlowchart.objects.create(
            rulebook=self.rulebook, edition=self.edition, ruleset=ruleset,
            detail="detailed", **kwargs,
        )

    def test_regenerated_chart_replaces_the_old_row(self):
        """同一個 (rulebook, ruleset) 換了新 PK 送過來，不該撞 unique constraint。"""
        old = self._chart(react_flow_json={"nodes": [{"id": "old"}], "edges": []})
        incoming = self._incoming(react_flow_json={"nodes": [{"id": "new"}], "edges": []})

        resp = self._post(_payload([incoming]))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["result"], "ok", resp.json().get("errors"))
        charts = RulebookFlowchart.objects.filter(rulebook=self.rulebook)
        self.assertEqual([c.id for c in charts], [incoming.id])
        self.assertEqual(charts[0].react_flow_json["nodes"][0]["id"], "new")
        self.assertFalse(RulebookFlowchart.objects.filter(pk=old.pk).exists())

    def test_member_suggestions_survive_the_replacement(self):
        """FlowchartSuggestion 是 CASCADE，且只存在 VPS——換圖不能把它一起刪掉。"""
        old = self._chart()
        sug = FlowchartSuggestion.objects.create(
            flowchart=old, edition=self.edition, ruleset=old.ruleset,
            content="第 3 步少了擲骰",
        )
        incoming = self._incoming(ruleset=old.ruleset)

        resp = self._post(_payload([incoming]))

        self.assertEqual(resp.json()["result"], "ok", resp.json().get("errors"))
        sug.refresh_from_db()
        self.assertEqual(sug.flowchart_id, incoming.id)
        self.assertEqual(sug.content, "第 3 步少了擲骰")

    def test_same_pk_is_still_a_plain_update(self):
        """PK 沒變時走原本的 update 路徑，不該有任何刪除。"""
        chart = self._chart(react_flow_json={"nodes": [], "edges": []})
        chart.react_flow_json = {"nodes": [{"id": "n1"}], "edges": []}

        resp = self._post(_payload([chart]))

        body = resp.json()
        self.assertEqual(body["result"], "ok", body.get("errors"))
        self.assertEqual(body["updated"], 1)
        self.assertEqual(body["created"], 0)
        chart.refresh_from_db()
        self.assertEqual(chart.react_flow_json["nodes"][0]["id"], "n1")

    def test_other_rulesets_are_left_alone(self):
        """只讓出撞到的那個 ruleset，同一本 rulebook 的其他圖不受影響。"""
        keep = self._chart(ruleset="Full")
        old = self._chart(ruleset="First time playing")
        incoming = self._incoming()

        resp = self._post(_payload([incoming]))

        self.assertEqual(resp.json()["result"], "ok", resp.json().get("errors"))
        self.assertTrue(RulebookFlowchart.objects.filter(pk=keep.pk).exists())
        self.assertEqual(RulebookFlowchart.objects.get(pk=keep.pk).ruleset, "Full")
        self.assertFalse(RulebookFlowchart.objects.filter(pk=old.pk).exists())
        self.assertEqual(RulebookFlowchart.objects.count(), 2)


class SyncScriptUpsertTests(TestCase):
    """RulebookScript 的 natural key 是 (rulebook, ruleset, language)——同一個坑。"""

    @classmethod
    def setUpTestData(cls):
        cls.tribe, _ = Tribe.objects.get_or_create(
            pk=1, defaults={"name": "Sync test tribe", "language": None},
        )
        # 明確指定 pk：seed 用的 Tribe 是帶 pk 寫進去的，Postgres 的 sequence 還停在 1，
        # 這裡用自動 pk 會撞到那一筆。
        cls.tribe_ja = Tribe.objects.create(
            pk=90001, name="Sync test tribe ja", language="ja-st",
        )
        cls.user = get_user_model().objects.create_user(
            username="syncbot2", email="syncbot2@example.com", password="x",
        )
        cls.game = Game.objects.create(canonical_name="Catan script")
        cls.edition = Edition.objects.create(
            game=cls.game, name="Catan script", slug="catan-script-test",
        )
        cls.rulebook = Rulebook.objects.create(edition=cls.edition, language=cls.tribe)

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("sync-game-data")

    def _post(self, payload):
        return self.client.post(self.url, data=payload, content_type="application/json")

    def _script(self, ruleset="basic", language=None, **kwargs):
        return RulebookScript.objects.create(
            rulebook=self.rulebook, edition=self.edition, ruleset=ruleset,
            language=language or self.tribe, is_published=True, **kwargs,
        )

    def _incoming(self, ruleset="basic", language=None, **kwargs):
        now = timezone.now()
        return RulebookScript(
            id=uuid.uuid4(), rulebook=self.rulebook, edition=self.edition,
            ruleset=ruleset, language=language or self.tribe, is_published=True,
            created_at=now, updated_at=now, **kwargs,
        )

    def test_regenerated_script_replaces_the_old_row(self):
        old = self._script(script_text="old text")
        incoming = self._incoming(script_text="new text")

        resp = self._post(_payload([incoming], "game.rulebookscript"))

        self.assertEqual(resp.json()["result"], "ok", resp.json().get("errors"))
        scripts = RulebookScript.objects.filter(rulebook=self.rulebook)
        self.assertEqual([s.id for s in scripts], [incoming.id])
        self.assertEqual(scripts[0].script_text, "new text")
        self.assertFalse(RulebookScript.objects.filter(pk=old.pk).exists())

    def test_other_language_is_a_separate_row(self):
        """language 也是 natural key 的一部分，別的語言版本不該被當成撞到。"""
        ja = self._script(language=self.tribe_ja, script_text="日本語")
        old = self._script(script_text="old")
        incoming = self._incoming(script_text="new")

        resp = self._post(_payload([incoming], "game.rulebookscript"))

        self.assertEqual(resp.json()["result"], "ok", resp.json().get("errors"))
        self.assertTrue(RulebookScript.objects.filter(pk=ja.pk).exists())
        self.assertEqual(RulebookScript.objects.get(pk=ja.pk).script_text, "日本語")
        self.assertFalse(RulebookScript.objects.filter(pk=old.pk).exists())
        self.assertEqual(RulebookScript.objects.count(), 2)

    def test_script_pointing_at_a_replaced_flowchart_keeps_its_source(self):
        """流程圖被換掉時，講稿的 source_flowchart 要跟著轉掛，不是被設成 NULL。"""
        chart = RulebookFlowchart.objects.create(
            rulebook=self.rulebook, edition=self.edition, ruleset="basic",
            detail="detailed",
        )
        script = self._script(source_flowchart=chart)
        now = timezone.now()
        incoming_chart = RulebookFlowchart(
            id=uuid.uuid4(), rulebook=self.rulebook, edition=self.edition,
            ruleset="basic", detail="detailed",
            created_at=now, updated_at=now,
        )

        resp = self._post(_payload([incoming_chart]))

        self.assertEqual(resp.json()["result"], "ok", resp.json().get("errors"))
        script.refresh_from_db()
        self.assertEqual(script.source_flowchart_id, incoming_chart.id)


class SyncFlowchartTextTranslationTests(TestCase):
    """
    FlowchartTextTranslation 的 PK 是 AutoField，本機與 VPS 的序號各自獨立；
    gc_flowchart_translations ＋重譯會刪掉再新建，兩邊序號早就漂開了。
    同一個 text_hash 在 VPS 上掛著別的 PK，pk-based exists 檢查看不到，
    寫入就撞 game_flowcharttexttranslation_text_hash_key。
    """

    HASH = "4946e061c5e1dc149f41c7e5b423798dcfc4ce501d4dfd9a5068a9872ef446d2"

    @classmethod
    def setUpTestData(cls):
        # Member.tribe 的 default=1 指向 migration 種下的 Tribe，整包測試一起跑時
        # 可能已經不在（同 SyncFlowchartUpsertTests 的註解），所以先自己確保它存在。
        Tribe.objects.get_or_create(
            pk=1, defaults={"name": "Sync test tribe", "language": None},
        )
        cls.user = get_user_model().objects.create_user(
            username="syncbot-text", email="syncbot-text@example.com", password="x",
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("sync-game-data")

    def _post(self, objs):
        return self.client.post(
            self.url,
            data=_payload(objs, model_label="game.flowcharttexttranslation"),
            content_type="application/json",
        )

    def _row(self, text_hash=None, **kwargs):
        return FlowchartTextTranslation.objects.create(
            text_hash=text_hash or self.HASH,
            source_text=kwargs.pop("source_text", "Take 1 tile"),
            source_lang=kwargs.pop("source_lang", "en"),
            **kwargs,
        )

    def _incoming(self, pk, text_hash=None, **kwargs):
        now = timezone.now()
        return FlowchartTextTranslation(
            pk=pk, text_hash=text_hash or self.HASH,
            source_text=kwargs.pop("source_text", "Take 1 tile"),
            source_lang=kwargs.pop("source_lang", "en"),
            created_at=now, updated_at=now, **kwargs,
        )

    def test_drifted_pk_replaces_the_row_with_the_same_hash(self):
        """同 text_hash 換了新 PK 送過來，要取代舊 row 而不是撞 unique constraint。"""
        old = self._row(translations={"en": "Take 1 tile", "zh": "舊譯文"})
        incoming = self._incoming(
            old.pk + 1000, translations={"en": "Take 1 tile", "zh": "拿 1 片板塊"},
            is_manual=True,
        )

        resp = self._post([incoming])

        body = resp.json()
        self.assertEqual(body["result"], "ok", body.get("errors"))
        rows = FlowchartTextTranslation.objects.filter(text_hash=self.HASH)
        self.assertEqual([r.pk for r in rows], [incoming.pk])
        self.assertEqual(rows[0].translations["zh"], "拿 1 片板塊")
        self.assertTrue(rows[0].is_manual)
        self.assertFalse(FlowchartTextTranslation.objects.filter(pk=old.pk).exists())

    def test_hash_moving_onto_an_existing_pk_still_works(self):
        """
        PK 已存在但內容換成別人的 text_hash：UPDATE 也會撞 unique，
        所以衝突清理不能只在 INSERT 時跑。
        """
        other_hash = "b" * 64
        stale = self._row(text_hash=other_hash, source_text="Draw a card")
        target = self._row(text_hash="a" * 64, source_text="old text")
        incoming = self._incoming(
            target.pk, text_hash=other_hash, source_text="Draw a card",
            translations={"zh": "抽一張牌"},
        )

        resp = self._post([incoming])

        body = resp.json()
        self.assertEqual(body["result"], "ok", body.get("errors"))
        self.assertFalse(FlowchartTextTranslation.objects.filter(pk=stale.pk).exists())
        target.refresh_from_db()
        self.assertEqual(target.text_hash, other_hash)
        self.assertEqual(target.translations["zh"], "抽一張牌")

    def test_other_hashes_are_left_alone(self):
        """只清掉撞到的那個 hash，其他譯文不受影響。"""
        keep = self._row(text_hash="c" * 64, source_text="Pass the dice")
        old = self._row()
        incoming = self._incoming(old.pk + 1000)

        resp = self._post([incoming])

        self.assertEqual(resp.json()["result"], "ok", resp.json().get("errors"))
        keep.refresh_from_db()
        self.assertEqual(keep.source_text, "Pass the dice")
        self.assertEqual(FlowchartTextTranslation.objects.count(), 2)


class SyncFlowchartLinkedEditionsTests(TestCase):
    """linked_editions（m2m）要跟著流程圖一起落地，否則 VPS 上的共用 edition 看不到圖。"""

    @classmethod
    def setUpTestData(cls):
        cls.tribe, _ = Tribe.objects.get_or_create(
            pk=1, defaults={"name": "Sync test tribe", "language": None},
        )
        cls.user = get_user_model().objects.create_user(
            username="syncbot-m2m", email="syncbot-m2m@example.com", password="x",
        )
        cls.game = Game.objects.create(canonical_name="Azul")
        cls.edition = Edition.objects.create(game=cls.game, name="Azul", slug="azul-test")
        cls.other = Edition.objects.create(game=cls.game, name="Azul JP", slug="azul-jp-test")
        cls.rulebook = Rulebook.objects.create(edition=cls.edition, language=cls.tribe)

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("sync-game-data")

    def test_linked_editions_land_on_the_receiver(self):
        chart = RulebookFlowchart.objects.create(
            rulebook=self.rulebook, edition=self.edition, ruleset="basic",
            detail="detailed",
        )
        chart.linked_editions.add(self.other)

        resp = self.client.post(
            self.url, data=_payload([chart]), content_type="application/json",
        )

        self.assertEqual(resp.json()["result"], "ok", resp.json().get("errors"))
        chart.refresh_from_db()
        self.assertEqual(
            list(chart.linked_editions.values_list("pk", flat=True)), [self.other.pk],
        )


class SyncGroupTests(TestCase):
    """auth.Group：權限用 natural key 送，同名群組沿用 VPS 既有的 PK。"""

    def setUp(self):
        # 建立 User 的 signal 會建 Member，Member.tribe 預設指向 pk=1
        Tribe.objects.get_or_create(pk=1, defaults={"name": "Sync test tribe", "language": None})
        user = get_user_model().objects.create_user(username="grpsync", password="x")
        self.client.force_login(user)
        self.url = reverse("sync-game-data")

    def _payload(self, group):
        from django.contrib.auth.models import Group
        return {
            "sync_type": "manual",
            "layers": [[{
                "model": "auth.group", "count": 1,
                "data": json.loads(django_serializers.serialize(
                    "json", Group.objects.filter(pk=group.pk), use_natural_foreign_keys=True,
                )),
            }]],
        }

    def test_permissions_are_sent_as_natural_keys(self):
        from django.contrib.auth.models import Group, Permission
        group = Group.objects.create(name="sender")
        group.permissions.add(Permission.objects.get(codename="view_rulebook"))
        payload = self._payload(group)
        self.assertEqual(
            payload["layers"][0][0]["data"][0]["fields"]["permissions"],
            [["view_rulebook", "game", "rulebook"]],
        )

    def test_same_name_different_pk_updates_existing_group_and_keeps_members(self):
        from django.contrib.auth.models import Group, Permission
        # VPS 上既有的群組（PK 與成員）
        vps = Group.objects.create(name="translators")
        member = get_user_model().objects.create_user(username="vpsmember", password="x")
        member.groups.add(vps)
        vps.permissions.add(Permission.objects.get(codename="view_edition"))

        # 本機同名但 PK 不同的群組，權限不同。同一個 DB 裡名稱唯一，所以先用別名建出
        # payload，再把名稱改成同名，模擬「本機的列不在這個 DB」。
        local = Group(pk=vps.pk + 100, name="translators_local")
        local.save()
        local.permissions.add(Permission.objects.get(codename="view_rulebook"))
        payload = self._payload(local)
        payload["layers"][0][0]["data"][0]["fields"]["name"] = "translators"
        local.delete()

        resp = self.client.post(self.url, data=payload, content_type="application/json")

        self.assertEqual(resp.json()["result"], "ok", resp.json().get("errors"))
        self.assertEqual(Group.objects.filter(name="translators").count(), 1)
        vps.refresh_from_db()
        self.assertEqual(
            list(vps.permissions.values_list("codename", flat=True)), ["view_rulebook"],
        )
        self.assertIn(vps, member.groups.all())
