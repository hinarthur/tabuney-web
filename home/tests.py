import json
import re

from django.template.loader import get_template
from django.test import TestCase, override_settings

from home.faq_content import (
    COMPARISON_ITEM,
    COMPARISON_TABLE,
    FAQ_ITEMS,
    translation_keys,
)
from translation.models import Translation, Tribe

JSONLD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)
TEMPLATE_QUESTION_RE = re.compile(r'{%\s*t\s+"faq\.([a-z_]+)\.question"\s*%}')


def jsonld_graph(response):
    """從回應裡挖出 JSON-LD @graph 的節點清單。"""
    match = JSONLD_RE.search(response.content.decode())
    assert match, "回應裡沒有 JSON-LD <script>"
    return json.loads(match.group(1))["@graph"]


def faq_node(response):
    for node in jsonld_graph(response):
        if node.get("@type") == "FAQPage":
            return node
    return None


class FaqContentTests(TestCase):
    """faq_content.FAQ_ITEMS 與 templates/faq.html 是兩份手寫清單，會漂開。"""

    def test_faq_items_match_template(self):
        source = get_template("faq.html").template.source
        in_template = TEMPLATE_QUESTION_RE.findall(source)

        self.assertEqual(sorted(in_template), sorted(FAQ_ITEMS))
        self.assertEqual(len(in_template), len(set(in_template)), "模板有重複的題目")


class FaqJsonLdTests(TestCase):
    def setUp(self):
        self.tribe = Tribe.objects.create(name="English", language="en")

    def seed(self, keys):
        Translation.objects.bulk_create(
            Translation(tribe=self.tribe, key=key, value=f"value for {key}")
            for key in keys
        )

    def test_faq_page_emits_faqpage_jsonld(self):
        self.seed(translation_keys())

        response = self.client.get("/faq/")
        self.assertEqual(response.status_code, 200)

        node = faq_node(response)
        self.assertIsNotNone(node, "沒有 FAQPage 節點")
        self.assertTrue(node["@id"].endswith("/faq/#webpage"))

        # FAQPage 必須取代 context processor 的通用 WebPage，而不是與它並存
        types = [n.get("@type") for n in jsonld_graph(response)]
        self.assertNotIn("WebPage", types)

        self.assertEqual(len(node["mainEntity"]), len(FAQ_ITEMS))
        self.assertEqual(
            node["mainEntity"][0]["name"], "value for faq.publisher.question"
        )
        self.assertEqual(
            node["mainEntity"][0]["acceptedAnswer"]["text"],
            "value for faq.publisher.answer",
        )

        # 比較表那題沒有單一 answer key，答案由表格攤平而來
        comparison = node["mainEntity"][FAQ_ITEMS.index(COMPARISON_ITEM)]
        answer = comparison["acceptedAnswer"]["text"]
        for row in COMPARISON_TABLE["rows"]:
            for cell in row:
                self.assertIn(f"faq.{COMPARISON_ITEM}.answer.{cell}", answer)

    def test_faq_jsonld_skips_missing_translations(self):
        self.seed(["faq.publisher.question", "faq.publisher.answer",
                   "faq.privacy.question"])

        node = faq_node(self.client.get("/faq/"))
        self.assertIsNotNone(node)

        # privacy 只有問題沒有答案，整題不該出現
        names = [q["name"] for q in node["mainEntity"]]
        self.assertEqual(names, ["value for faq.publisher.question"])

    def test_comparison_answer_needs_every_cell(self):
        keys = [k for k in translation_keys()
                if k != f"faq.{COMPARISON_ITEM}.answer.limited"]
        self.seed(keys)

        node = faq_node(self.client.get("/faq/"))
        names = [q["name"] for q in node["mainEntity"]]
        self.assertNotIn(f"value for faq.{COMPARISON_ITEM}.question", names)
        self.assertEqual(len(names), len(FAQ_ITEMS) - 1)

    def test_no_questions_falls_back_to_webpage(self):
        """翻譯還沒進 DB 時，不該吐出空 mainEntity 的 FAQPage。"""
        response = self.client.get("/faq/")

        self.assertIsNone(faq_node(response))
        types = [n.get("@type") for n in jsonld_graph(response)]
        self.assertIn("WebPage", types)


# sitemap section 是 cache_page 包起來的，而預設快取是 FileBasedCache（/tmp/django_cache），
# 同一個容器裡的 runserver 與測試共用同一份檔案 —— 不隔離的話測試會拿到開發伺服器
# 幾小時前存下的舊 sitemap。
@override_settings(CACHES={
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
})
class FaqSitemapTests(TestCase):
    def test_faq_in_static_sitemap(self):
        response = self.client.get("/sitemap-static.xml")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/faq/", response.content.decode())
