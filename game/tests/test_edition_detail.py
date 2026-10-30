"""EditionDetailView 的網址與分頁拆分行為。

四個分頁（rulesbot / flowchart / script / info）是四個獨立頁面：各自只渲染自己的
內容、只建構自己的 context。這份測試守的就是那條界線，以及拆分前就有的網址收斂
規則（舊 slug / 裸 UUID / 非規範分頁後綴一律 301）。

分頁列的「哪幾顆按鈕」由 selectors.edition_tab_flags() 的便宜 EXISTS 決定，而頁面
本身由 view 的完整建構決定——兩者的判準必須一致，否則會出現「按鈕在、點進去 404」。
test_tab_flags_match_actual_pages 就是在盯這件事。
"""
import re
import uuid

from django.test import TestCase
from django.urls import reverse

from game.models import Edition, Game, Rulebook, RulebookFlowchart, RulebookScript
from game.tests.flowchart_helpers import publish_flowchart
from translation.models import Tribe


FLOW_JSON = {
    "nodes": [
        {"id": "p1", "type": "group", "data": {"label": "Setup"}},
        {"id": "n1", "type": "action", "data": {"label": "Deal one card", "phase_id": "p1"}},
        {"id": "n2", "type": "action", "data": {"label": "Draw a card", "phase_id": "p1"}},
    ],
    "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
}


class EditionDetailTabsTests(TestCase):
    """四個分頁各自獨立。"""

    @classmethod
    def setUpTestData(cls):
        cls.tribe, _ = Tribe.objects.get_or_create(language="en")

        # 四個分頁都有內容的版本
        # 六項能力給值，info 分頁才會渲染雷達圖（has_skills）——那是這一頁的 marker
        cls.game = Game.objects.create(
            canonical_name="Full Game",
            adaptability=3, collaboration=3, communication=3,
            creativity=3, critical_thinking=3, problem_solving=3,
        )
        cls.full = Edition.objects.create(
            game=cls.game, name="Full Game", slug="full-game",
            summary="A summary that only the info tab should use.",
        )
        rb = Rulebook.objects.create(
            edition=cls.full, title="Full Game Rules", language=cls.tribe,
        )
        publish_flowchart(RulebookFlowchart.objects.create(
            rulebook=rb, ruleset="base",
            initial=True, react_flow_json=FLOW_JSON,
        ))
        RulebookScript.objects.create(
            rulebook=rb, language=cls.tribe, is_published=True,
            script_text="Welcome to the table.\nLet me set the scene.",
        )

        # 只有 rulesbot / info 的版本（沒有流程圖也沒有講稿）
        cls.bare_game = Game.objects.create(canonical_name="Bare Game")
        cls.bare = Edition.objects.create(
            game=cls.bare_game, name="Bare Game", slug="bare-game",
        )

    # ── 每頁只渲染自己的內容 ──────────────────────────────────────────

    # marker → 只有這一頁才該出現的 DOM 片段
    MARKERS = {
        "chat": 'id="chat-window"',
        "flowchart": "fc-viewer-rs",
        "script": 'class="script-pane"',
        "info": 'id="radar-chart"',
    }
    PATHS = {
        "chat": "/games/full-game/chat/",
        "flowchart": "/games/full-game/flowchart/",
        "script": "/games/full-game/script/",
        "info": "/games/full-game/",
    }

    def test_each_tab_renders_only_its_own_panel(self):
        for tab, path in self.PATHS.items():
            with self.subTest(tab=tab):
                html = self.client.get(path).content.decode()
                self.assertIn(self.MARKERS[tab], html)
                for other, marker in self.MARKERS.items():
                    if other != tab:
                        self.assertNotIn(
                            marker, html,
                            f"{path} 不該含有 {other} 分頁的內容（{marker}）",
                        )

    def test_each_tab_uses_its_own_template(self):
        expected = {
            "chat": "game/edition_detail_rulesbot.html",
            "flowchart": "game/edition_detail_flowchart.html",
            "script": "game/edition_detail_script.html",
            "info": "game/edition_detail_info.html",
        }
        for tab, path in self.PATHS.items():
            with self.subTest(tab=tab):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertTemplateUsed(r, expected[tab])
                # 每個 leaf 都繼承同一個 shell
                self.assertTemplateUsed(r, "game/edition_detail.html")

    def test_other_tabs_context_is_not_built(self):
        """非該分頁的重量級 context 不該存在——那正是拆分要省下來的成本。"""
        cases = {
            "chat": ("flowchart_charts", "script_data", "user_interaction"),
            "flowchart": ("chat_status", "script_data", "user_interaction"),
            "script": ("chat_status", "flowchart_charts", "user_interaction"),
            "info": ("chat_status", "flowchart_charts", "script_data"),
        }
        for tab, absent_keys in cases.items():
            with self.subTest(tab=tab):
                ctx = self.client.get(self.PATHS[tab]).context
                for key in absent_keys:
                    self.assertNotIn(
                        key, ctx, f"{tab} 分頁不該建構 {key}",
                    )

    def test_h1_is_unique_per_tab(self):
        """每頁剛好一個 h1，且四頁互不相同（分頁名稱接在版本名之後）。

        四頁的 h1 都只有版本名的話，等於四個網址對外宣告同一個主標題。
        """
        seen = {}
        for tab, path in self.PATHS.items():
            html = self.client.get(path).content.decode()
            h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S)
            self.assertEqual(len(h1s), 1, f"{path} 應該剛好一個 h1，實際 {len(h1s)} 個")
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h1s[0])).strip()
            self.assertIn("Full Game", text, f"{path} 的 h1 應該含版本名")
            seen[tab] = text
        self.assertEqual(len(set(seen.values())), 4, f"h1 有重複: {seen}")

    def test_panels_no_longer_carry_the_tab_heading(self):
        """分頁名稱只該出現在 h1，面板裡原本那個 h2 已經移除。"""
        for tab, path in self.PATHS.items():
            with self.subTest(tab=tab):
                html = self.client.get(path).content.decode()
                intro = re.search(
                    r'<div class="tab-section-intro">(.*?)</div>', html, re.S)
                self.assertIsNotNone(intro, f"{path} 少了 .tab-section-intro 說明段")
                self.assertNotIn("<h2", intro.group(1),
                                 f"{path} 的 .tab-section-intro 不該還有 h2")
                self.assertIn("<p>", intro.group(1),
                              f"{path} 的說明文字 p 應該保留")

    def test_no_duplicated_dom(self):
        """一份分頁列、一份面板、每個 id 只出現一次。

        以前桌機與手機各有一整套 DOM，靠 media query 顯示其中一套 —— 爬蟲看到的
        是兩份一樣的內容、每個 id 各兩個。這條測試就是不讓那個回來。
        """
        for tab, path in self.PATHS.items():
            with self.subTest(tab=tab):
                html = self.client.get(path).content.decode()

                self.assertEqual(
                    html.count('class="edition-main-tabs"'), 1, "分頁列不只一份")
                self.assertEqual(
                    html.count('class="main-tab-content active"'), 1, "面板不只一份")
                self.assertEqual(
                    html.count('class="tab-section-intro"'), 1, "說明段不只一份")

                # 這一頁自己的 DOM 裡不該有重複 id。base.html 的全站導覽本來就有
                # 一組 -desktop/-mobile 的頁首元素，不在這次統一的範圍內，所以只
                # 檢查 .edition-container 裡面。
                body = re.search(
                    r'<div class="container edition-container">(.*?)$', html, re.S)
                ids = re.findall(r'\sid="([^"]+)"', body.group(1))
                dupes = [i for i in set(ids) if ids.count(i) > 1]
                self.assertEqual(dupes, [], f"{path} 有重複 id: {dupes}")

    def test_flowchart_json_is_emitted_once_per_chart(self):
        """react_flow_json 是這一頁最大的 payload，一張圖只該輸出一份。"""
        html = self.client.get(self.PATHS["flowchart"]).content.decode()
        self.assertEqual(html.count('"reactFlowData"'), 1)
        self.assertIn('"mountId": "fc-viewer-rs0"', html)
        self.assertNotIn("fc-viewer-desktop", html)
        self.assertNotIn("fc-viewer-mobile", html)

    def test_meta_descriptions_are_all_different(self):
        """四頁描述一樣的話，拆頁對 GEO 就沒有意義。"""
        seen = set()
        for tab, path in self.PATHS.items():
            html = self.client.get(path).content.decode()
            start = html.index('<meta name="description" content="') + 34
            seen.add(html[start:html.index('">', start)])
        self.assertEqual(len(seen), 4, f"description 有重複: {seen}")

    # ── 分頁列 ───────────────────────────────────────────────────────

    def test_tab_strip_shows_all_four_tabs_on_every_page(self):
        for tab, path in self.PATHS.items():
            with self.subTest(tab=tab):
                html = self.client.get(path).content.decode()
                for suffix in ("", "flowchart/", "script/", "chat/"):
                    self.assertIn(f'href="/games/full-game/{suffix}"', html)

    def test_tab_strip_hides_missing_tabs(self):
        html = self.client.get("/games/bare-game/").content.decode()
        self.assertIn('href="/games/bare-game/chat/"', html)
        self.assertNotIn("/games/bare-game/flowchart/", html)
        self.assertNotIn("/games/bare-game/script/", html)

    def test_tab_flags_match_actual_pages(self):
        """便宜的 EXISTS 與完整建構不能漂開，否則按鈕與頁面會自相矛盾。"""
        for edition in (self.full, self.bare):
            ctx = self.client.get(f"/games/{edition.slug}/").context
            for flag, suffix in (("has_flowchart", "flowchart/"), ("has_script", "script/")):
                with self.subTest(edition=edition.slug, flag=flag):
                    status = self.client.get(
                        f"/games/{edition.slug}/{suffix}"
                    ).status_code
                    self.assertEqual(
                        ctx[flag], status == 200,
                        f"{edition.slug} 的 {flag}={ctx[flag]} 但該頁回 {status}",
                    )

    # ── 網址收斂 ─────────────────────────────────────────────────────

    def test_unknown_tab_404s(self):
        self.assertEqual(self.client.get("/games/full-game/bogus/").status_code, 404)

    def test_missing_content_tab_404s(self):
        for suffix in ("flowchart/", "script/"):
            with self.subTest(suffix=suffix):
                self.assertEqual(
                    self.client.get(f"/games/bare-game/{suffix}").status_code, 404,
                )

    def test_default_tab_alias_redirects(self):
        r = self.client.get("/games/full-game/info/")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "/games/full-game/")

    def test_rulesbot_alias_redirects_to_chat(self):
        r = self.client.get("/games/full-game/rulesbot/")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "/games/full-game/chat/")

    def test_bare_uuid_redirects(self):
        r = self.client.get(f"/games/{self.full.id}/")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "/games/full-game/")

    def test_legacy_singular_path_redirects(self):
        """TJsite/urls.py 的 /game/<slug>/ 沒有 tab kwarg，current_tab() 要吃得下。"""
        r = self.client.get("/game/full-game/")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "/games/full-game/")

    def test_unknown_slug_404s(self):
        self.assertEqual(
            self.client.get(f"/games/{uuid.uuid4()}/").status_code, 404,
        )

    def test_query_string_survives_redirect(self):
        r = self.client.get("/games/full-game/info/?ref=x")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "/games/full-game/?ref=x")

    # ── SEO 佈線 ─────────────────────────────────────────────────────

    def test_canonical_is_per_tab(self):
        for path in self.PATHS.values():
            with self.subTest(path=path):
                html = self.client.get(path).content.decode()
                self.assertIn(f'<link rel="canonical" href="', html)
                self.assertIn(f'{path}"', html)

    def test_sitemap_urls_still_reverse(self):
        """URL name 與 kwargs 不能改，game/sitemaps.py 的類別都靠 reverse()。"""
        self.assertEqual(
            reverse("games:edition-detail", kwargs={"slug": "full-game"}),
            "/games/full-game/",
        )
        for tab in ("flowchart", "chat"):
            self.assertEqual(
                reverse("games:edition-detail-tab",
                        kwargs={"slug": "full-game", "tab": tab}),
                f"/games/full-game/{tab}/",
            )


class TemplateCommentLintTests(TestCase):
    """Django 的 {# #} 只到行尾，跨行寫的話第二行起會被當成內容渲染出去。

    這個錯誤不會噴任何例外（除非註解裡剛好有 {% %} 標籤），只會安靜地把註解文字
    印在頁面上 —— flowchart 的文字版大綱就中過一次，而那正是給爬蟲讀的內容。
    跨行註解一律用 {% comment %}。
    """

    def test_no_multiline_hash_comments_in_templates(self):
        import os
        from django.conf import settings

        offenders = []
        for tpl_dir in settings.TEMPLATES[0]["DIRS"]:
            for dirpath, _dirnames, filenames in os.walk(tpl_dir):
                for name in filenames:
                    if not name.endswith((".html", ".txt")):
                        continue
                    path = os.path.join(dirpath, name)
                    with open(path, encoding="utf-8") as fh:
                        lines = fh.read().splitlines()
                    for lineno, line in enumerate(lines, 1):
                        i = line.find("{#")
                        while i != -1:
                            if "#}" not in line[i + 2:]:
                                offenders.append(
                                    "%s:%d" % (os.path.relpath(path, tpl_dir), lineno))
                                break
                            i = line.find("{#", line.find("#}", i) + 2)

        self.assertEqual(
            offenders, [],
            "這些 {# #} 沒有在同一行閉合，第二行起會被渲染出來；改用 "
            "{%% comment %%}：%s" % offenders,
        )
