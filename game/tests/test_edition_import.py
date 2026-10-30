"""版本輸入（game/edition_import.py）：解析、比對、只補空白、全有或全無。"""
from django.test import TestCase

from commerce.models import Currency
from game.edition_import import run_import
from game.models import Edition, EditionRole, Entity, Game, GameTitle, Rulebook
from translation.models import Region, Tribe


SAMPLE = """
# 註解
[game]
name: Catan
bgg_id: 13
kind: standalone
players: 3-4
playtime: 60-120
title: en | Catan *
title: zh | 卡坦島

   [edition]
   name: 繁中第五版
   language: zh
   packaging_language: zh
   packaging_language: en
   region: TWN
   release_year: 2023
   barcode: 4716000000001
   msrp: 1280 TWD
   primary: yes
   publisher: Swan Panasia
   designer: Klaus Teuber
   summary: <<<
第一行
第二行
>>>

   [rulebook]
   title: 遊戲規則
   language: zh
   url: https://example.com/catan-zh.pdf
"""


def counts():
    return (Game.objects.count(), GameTitle.objects.count(), Edition.objects.count(),
            Entity.objects.count(), EditionRole.objects.count(), Rulebook.objects.count())


class EditionImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zh = Tribe.objects.create(name="zh - 華文", language="zh")
        cls.en = Tribe.objects.create(name="en - English", language="en")
        Region.objects.create(code="TWN", name="Taiwan")
        Currency.objects.create(code="TWD", symbol="NT$", name="Taiwan Dollar")

    def test_commit_creates_everything(self):
        rep = run_import(SAMPLE, commit=True)
        self.assertFalse(rep.has_errors, rep.errors)
        self.assertEqual(counts(), (1, 2, 1, 2, 2, 1))
        g = Game.objects.get()
        self.assertEqual((g.min_players, g.max_players, g.min_playtime, g.max_playtime), (3, 4, 60, 120))
        self.assertTrue(g.titles.get(title="Catan").is_primary)
        e = Edition.objects.get()
        self.assertEqual(e.summary, "第一行\n第二行")
        self.assertEqual(e.msrp_currency.code, "TWD")
        self.assertTrue(e.is_primary)
        self.assertEqual(e.packaging_languages.count(), 2)
        self.assertEqual(Entity.objects.get(name="Swan Panasia").entity_type, "company")
        self.assertEqual(Entity.objects.get(name="Klaus Teuber").entity_type, "individual")
        self.assertEqual(Rulebook.objects.get().status, "pending")

    def test_preview_writes_nothing(self):
        rep = run_import(SAMPLE, commit=False)
        self.assertFalse(rep.has_errors)
        self.assertEqual(counts(), (0, 0, 0, 0, 0, 0))

    def test_reimport_is_idempotent(self):
        run_import(SAMPLE, commit=True)
        before = counts()
        rep = run_import(SAMPLE, commit=True)
        self.assertFalse(rep.has_errors, rep.errors)
        self.assertEqual(counts(), before)

    def test_existing_edition_only_fills_blanks(self):
        run_import(SAMPLE, commit=True)
        text = SAMPLE.replace("age: 10", "").replace(
            "barcode: 4716000000001", "barcode: 4716000000001\nage: 10")
        text = text.replace("msrp: 1280 TWD", "msrp: 999 TWD")
        rep = run_import(text, commit=True)
        self.assertFalse(rep.has_errors, rep.errors)
        e = Edition.objects.get()
        self.assertEqual(e.age, 10)                    # 空白 → 補上
        self.assertEqual(int(e.msrp), 1280)            # 已有 → 不覆蓋
        self.assertTrue(any(i["level"] == "skip" for i in rep.items))

    def test_m2m_addition_touches_updated_at(self):
        run_import(SAMPLE, commit=True)
        e = Edition.objects.get()
        old = e.updated_at
        Tribe.objects.create(name="ja - 日本語", language="ja")
        rep = run_import(SAMPLE.replace("packaging_language: en", "packaging_language: ja"), commit=True)
        self.assertFalse(rep.has_errors, rep.errors)
        e.refresh_from_db()
        self.assertEqual(e.packaging_languages.count(), 3)
        self.assertGreater(e.updated_at, old)

    def test_same_name_year_different_language_is_error(self):
        run_import(SAMPLE, commit=True)
        rep = run_import(SAMPLE.replace("language: zh\n   packaging", "language: en\n   packaging"), commit=True)
        self.assertTrue(rep.has_errors)
        self.assertIn("語言不同", rep.errors[0]["text"])

    def test_same_name_different_year_warns_and_creates(self):
        run_import(SAMPLE, commit=True)
        text = SAMPLE.replace("release_year: 2023", "release_year: 2024").replace("barcode: 4716000000001", "")
        rep = run_import(text, commit=True)
        self.assertFalse(rep.has_errors, rep.errors)
        self.assertEqual(Edition.objects.count(), 2)
        self.assertTrue(rep.warnings)

    def test_barcode_owned_by_other_edition_is_error(self):
        run_import(SAMPLE, commit=True)
        rep = run_import(SAMPLE.replace("release_year: 2023", "release_year: 2024"), commit=True)
        self.assertTrue(rep.has_errors)
        self.assertEqual(Edition.objects.count(), 1)

    def test_all_or_nothing_on_bad_language(self):
        two = SAMPLE + "\n[game]\nname: Second\n[edition]\nname: x\nlanguage: xx\nrelease_year: 2020\n"
        rep = run_import(two, commit=True)
        self.assertTrue(rep.has_errors)
        self.assertEqual(counts(), (0, 0, 0, 0, 0, 0))   # 第一款遊戲也沒寫進去

    def test_missing_required_fields_collected_together(self):
        rep = run_import("[game]\nname: A\n[edition]\nlanguage: zh\n[rulebook]\ntitle: t\n", commit=True)
        msgs = " ".join(i["text"] for i in rep.errors)
        self.assertIn("name", msgs)
        self.assertIn("release_year", msgs)
        self.assertEqual(counts(), (0, 0, 0, 0, 0, 0))

    def test_format_errors_report_line_numbers(self):
        rep = run_import("[game]\nname: A\nrelase_year: 1\n[edition]\n", commit=False)
        self.assertEqual(rep.errors[0]["line"], 3)
        self.assertIn("relase_year", rep.errors[0]["text"])

    def test_unclosed_multiline_and_orphan_sections(self):
        rep = run_import("[edition]\nname: x\n", commit=False)
        self.assertIn("沒有 [game]", rep.errors[0]["text"])
        rep = run_import("[game]\nname: A\n[edition]\nsummary: <<<\nabc\n", commit=False)
        self.assertTrue(any(">>>" in i["text"] for i in rep.errors))

    def test_similar_entity_name_warns(self):
        Entity.objects.create(name="Swan Panasia", entity_type="company")
        rep = run_import(SAMPLE.replace("publisher: Swan Panasia", "publisher: Swanpanasia"), commit=False)
        self.assertFalse(rep.has_errors, rep.errors)
        self.assertTrue(any("很像" in i["text"] for i in rep.warnings))

    def test_parent_resolves_by_bgg_id(self):
        run_import(SAMPLE, commit=True)
        exp = ("[game]\nname: Catan Seafarers\nkind: expansion\nparent: 13\n")
        rep = run_import(exp, commit=True)
        self.assertFalse(rep.has_errors, rep.errors)
        self.assertEqual(Game.objects.get(canonical_name="Catan Seafarers").parent_game.bgg_id, 13)
        rep = run_import("[game]\nname: Orphan\nparent: Nope\n", commit=False)
        self.assertTrue(rep.has_errors)
