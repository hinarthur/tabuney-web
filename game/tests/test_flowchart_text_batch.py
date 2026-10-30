"""
Flowchart 文字：待翻譯清單與批次填寫頁（FlowchartTextTranslationAdmin.translate_*）。

重點：待翻譯 = 這張圖的文字 − 已有完整譯文的列；文字以 hash 跨圖共用，所以變體圖
只會剩下新出現的幾段。
"""

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from game.models import (
    Edition, FlowchartTextTranslation, Game, Rulebook, RulebookFlowchart,
)
from game.rag.flowchart.i18n import LANGS, compute_hash, pending_counts, pending_translations
from translation.models import Tribe


def _flow(*labels):
    nodes = [{"id": "p1", "type": "group", "data": {"label": "Setup"}}]
    for i, label in enumerate(labels):
        nodes.append({
            "id": f"n{i}", "type": "action",
            "data": {"label": label, "phase_id": "p1", "phase_label": "Preparation"},
        })
    return {"nodes": nodes, "edges": []}


def _full(text, src="en"):
    return {code: text for code in LANGS}


def _row(text, translations, src="en", manual=False):
    return FlowchartTextTranslation.objects.create(
        text_hash=compute_hash(text), source_text=text, source_lang=src,
        translations=translations, is_manual=manual,
    )


def _user(username, *codenames):
    user = User.objects.create_user(username=username, password="pw", is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(
        content_type__app_label="game", codename__in=codenames,
    ))
    return User.objects.get(pk=user.pk)


class BatchTranslateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tribe, _ = Tribe.objects.get_or_create(pk=1, defaults={"language": "en", "name": "English"})
        # 翻譯員：只有譯文的權限，沒有流程圖本身的任何權限
        cls.translator = _user(
            "translator", "view_flowcharttexttranslation", "change_flowcharttexttranslation",
        )
        cls.nobody = _user("nobody", "view_flowcharttexttranslation")
        cls.game = Game.objects.create(canonical_name="Batch Game")
        cls.edition = Edition.objects.create(game=cls.game, name="Batch Game", slug="batch-game")
        cls.rulebook = Rulebook.objects.create(edition=cls.edition, language=cls.tribe, title="Batch Rules")

    def _chart(self, ruleset, *labels):
        return RulebookFlowchart.objects.create(
            rulebook=self.rulebook, edition=self.edition, ruleset=ruleset,
            react_flow_json=_flow(*labels),
        )

    def _complete(self, *texts):
        for t in texts:
            _row(t, _full(t))

    def _url(self, chart, **qs):
        url = reverse("admin:game_flowcharttexttranslation_translate_chart", args=[chart.pk])
        return url + (("?" + "&".join(f"{k}={v}" for k, v in qs.items())) if qs else "")

    # ── 待翻譯的計算 ──

    def test_variant_only_lists_the_new_texts(self):
        shared = [f"Shared step {i}" for i in range(99)]
        self._complete("Setup", "Preparation", "basic", "variant", *shared)
        base = self._chart("basic", *shared)
        variant = self._chart("variant", *shared, "A brand new rule", "Another new rule")

        pending = pending_translations([base, variant])

        self.assertEqual(pending[base.pk], [])
        self.assertEqual(
            [p.source_text for p in pending[variant.pk]], ["A brand new rule", "Another new rule"],
        )
        self.assertEqual(pending_counts([base, variant]), {base.pk: 0, variant.pk: 2})

    def test_partial_row_reports_only_missing_languages(self):
        self._complete("Setup", "Preparation", "basic")
        _row("Draw a card", {"en": "Draw a card", "zh": "抽一張牌", "ja": "カードを引く"})
        chart = self._chart("basic", "Draw a card")

        (item,) = pending_translations([chart])[chart.pk]

        self.assertEqual(item.missing, ["fr", "de", "es"])
        self.assertEqual(item.current["zh"], "抽一張牌")
        self.assertTrue(item.has_row)

    def test_text_without_row_is_pending_in_every_other_language(self):
        self._complete("Setup", "Preparation", "basic")
        chart = self._chart("basic", "Brand new")

        (item,) = pending_translations([chart])[chart.pk]

        self.assertFalse(item.has_row)
        self.assertEqual(item.missing, ["zh", "ja", "fr", "de", "es"])

    def test_ruleset_name_counts_with_english_source(self):
        self._complete("Setup", "Preparation")
        chart = self._chart("Solo variant", "x")   # "x" 與 "Solo variant" 都沒有列
        texts = {p.source_text: p for p in pending_translations([chart])[chart.pk]}
        self.assertIn("Solo variant", texts)
        self.assertEqual(texts["Solo variant"].source_lang, "en")
        self.assertEqual(texts["Solo variant"].usages, ["Ruleset 名稱"])

    def test_usages_describe_where_the_text_appears(self):
        self._complete("Setup", "Preparation", "basic")
        chart = self._chart("basic", "Place Anna the Brave on the board")
        (item,) = pending_translations([chart])[chart.pk]
        self.assertEqual(item.usages, ["節點（action）・Preparation・label"])

    def test_pending_query_count_is_constant(self):
        charts = [self._chart(f"rs{i}", *[f"text {i}-{j}" for j in range(5)]) for i in range(4)]
        with self.assertNumQueries(1):
            pending_translations(charts)

    # ── 批次頁 ──

    def test_translator_without_flowchart_perms_can_open_and_sees_context(self):
        self._complete("Setup", "Preparation", "basic")
        chart = self._chart("basic", "Brand new")
        self.client.force_login(self.translator)

        resp = self.client.get(self._url(chart))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Batch Game")
        self.assertContains(resp, "Batch Rules")
        self.assertContains(resp, "Brand new")
        self.assertContains(resp, "節點（action）・Preparation・label")
        # 但進不了流程圖本身的頁面
        self.assertEqual(
            self.client.get(reverse("admin:game_rulebookflowchart_change", args=[chart.pk])).status_code,
            403,
        )

    def test_user_without_change_permission_gets_403(self):
        chart = self._chart("basic", "x")
        self.client.force_login(self.nobody)
        self.assertEqual(self.client.get(self._url(chart)).status_code, 403)
        self.assertEqual(self.client.post(self._url(chart), {}).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("admin:game_flowcharttexttranslation_translate")).status_code, 403,
        )

    def test_save_creates_missing_rows_and_updates_partial_ones(self):
        self._complete("Setup", "Preparation", "basic")
        _row("Draw a card", {"en": "Draw a card", "zh": "抽一張牌"})
        chart = self._chart("basic", "Draw a card", "Place Anna on the board")
        self.client.force_login(self.translator)

        h_new = compute_hash("Place Anna on the board")
        h_part = compute_hash("Draw a card")
        resp = self.client.post(self._url(chart), {
            f"t__{h_new}__zh": "把 Anna 放到版圖上",
            f"t__{h_new}__ja": "Anna を盤面に置く",
            f"t__{h_part}__ja": "カードを引く",
            f"t__{h_part}__zh": "",        # 留空不得清掉既有譯文
        })

        self.assertEqual(resp.status_code, 302)
        new = FlowchartTextTranslation.objects.get(text_hash=h_new)
        self.assertEqual(new.translations["en"], "Place Anna on the board")   # 來源語原文
        self.assertEqual(new.translations["zh"], "把 Anna 放到版圖上")
        self.assertTrue(new.is_manual)
        part = FlowchartTextTranslation.objects.get(text_hash=h_part)
        self.assertEqual(part.translations["zh"], "抽一張牌")
        self.assertEqual(part.translations["ja"], "カードを引く")

    def test_empty_save_changes_nothing(self):
        self._complete("Setup", "Preparation", "basic")
        chart = self._chart("basic", "Brand new")
        self.client.force_login(self.translator)
        before = FlowchartTextTranslation.objects.count()

        self.client.post(self._url(chart), {})

        self.assertEqual(FlowchartTextTranslation.objects.count(), before)

    def test_cannot_write_hashes_that_are_not_in_this_chart(self):
        self._complete("Setup", "Preparation", "basic")
        chart = self._chart("basic", "Brand new")
        stranger = compute_hash("Not part of this chart")
        self.client.force_login(self.translator)

        self.client.post(self._url(chart), {f"t__{stranger}__zh": "不該被寫入"})

        self.assertFalse(FlowchartTextTranslation.objects.filter(text_hash=stranger).exists())

    def test_source_language_cell_cannot_be_overwritten(self):
        self._complete("Setup", "Preparation", "basic")
        chart = self._chart("basic", "Brand new")
        self.client.force_login(self.translator)

        h = compute_hash("Brand new")
        self.client.post(self._url(chart), {f"t__{h}__en": "tampered", f"t__{h}__zh": "全新"})

        row = FlowchartTextTranslation.objects.get(text_hash=h)
        self.assertEqual(row.translations["en"], "Brand new")
        self.assertEqual(row.translations["zh"], "全新")

    def test_after_saving_everything_the_chart_is_complete(self):
        self._complete("Setup", "Preparation", "basic")
        chart = self._chart("basic", "Brand new")
        self.client.force_login(self.translator)
        h = compute_hash("Brand new")

        self.client.post(self._url(chart), {f"t__{h}__{code}": f"{code}!" for code in LANGS if code != "en"})

        self.assertEqual(pending_translations([chart])[chart.pk], [])

    def test_picker_lists_only_charts_with_pending_texts(self):
        self._complete("Setup", "Preparation", "basic", "done")
        self._chart("basic", "done")                 # 完整
        todo = self._chart("todo", "needs work")     # 缺譯文
        self.client.force_login(self.translator)

        resp = self.client.get(reverse("admin:game_flowcharttexttranslation_translate"))

        self.assertEqual([r["chart"].pk for r in resp.context["rows"]], [todo.pk])
        resp = self.client.get(reverse("admin:game_flowcharttexttranslation_translate") + "?all=1")
        self.assertEqual(len(resp.context["rows"]), 2)

    def test_lang_filter_only_shows_texts_missing_that_language(self):
        self._complete("Setup", "Preparation", "basic")
        _row("Has ja", {c: "x" for c in LANGS if c != "fr"})
        _row("Has fr", {c: "x" for c in LANGS if c != "ja"})
        chart = self._chart("basic", "Has ja", "Has fr")
        self.client.force_login(self.translator)

        resp = self.client.get(self._url(chart, lang="ja"))

        self.assertEqual([i["text"] for i in resp.context["items"]], ["Has fr"])

    # ── Flowchart text 清單的篩選 ──

    def test_list_filters_by_chart_rulebook_and_completeness(self):
        self._complete("Setup", "Preparation", "basic")
        _row("In chart", {"en": "In chart"})
        _row("Elsewhere", {"en": "Elsewhere"})
        chart = self._chart("basic", "In chart")
        self.client.force_login(self.translator)
        url = reverse("admin:game_flowcharttexttranslation_changelist")

        def shown(**qs):
            resp = self.client.get(url, qs)
            self.assertEqual(resp.status_code, 200, qs)
            return {o.source_text for o in resp.context["cl"].result_list}

        self.assertEqual(shown(chart=chart.pk), {"Setup", "Preparation", "basic", "In chart"})
        self.assertEqual(shown(rulebook=self.rulebook.pk), {"Setup", "Preparation", "basic", "In chart"})
        self.assertEqual(shown(chart=chart.pk, completeness="incomplete"), {"In chart"})
        self.assertEqual(shown(completeness="missing_ja"), {"In chart", "Elsewhere"})
        self.assertNotIn("Elsewhere", shown(chart=chart.pk))
        self.assertEqual(shown(chart="not-a-uuid"), set())

    def test_flowchart_page_shows_pending_count_only_to_those_who_can_translate(self):
        self._complete("Setup", "Preparation", "basic")
        chart = self._chart("basic", "Brand new")
        editor = _user("fc_editor", "view_rulebookflowchart", "change_rulebookflowchart")
        both = _user(
            "fc_both", "view_rulebookflowchart", "change_rulebookflowchart",
            "view_flowcharttexttranslation", "change_flowcharttexttranslation",
        )
        url = reverse("admin:game_rulebookflowchart_change", args=[chart.pk])

        self.client.force_login(editor)
        self.assertNotContains(self.client.get(url), "前往批次填寫")
        self.client.force_login(both)
        resp = self.client.get(url)
        self.assertContains(resp, "前往批次填寫")
        self.assertContains(resp, "1 段待翻譯")
