from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from game.models import Edition

# 兩個 Edition sitemap 的 location / lastmod 只用到這些欄位
_SITEMAP_FIELDS = ("id", "slug", "updated_at")


class EditionSitemap(Sitemap):
    """
    每個版本詳細頁 × 每種語言。

    i18n / alternates / x_default 是 django.contrib.sitemaps 內建的，會自動產出
    每個語言前綴的 <url> 以及 xhtml:link rel="alternate" hreflang。不要手刻 XML。
    """

    # 站台一律走 HTTPS。不指定的話 sitemap 會沿用請求的 scheme，
    # 一旦反向代理的 header 沒設好就會產出 http:// 的網址。
    protocol = "https"

    changefreq = "weekly"
    priority = 0.8
    limit = 2000          # 搭配 sitemap index 分檔
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        # i18n=True 會把整個 queryset 展開成 list（index 算頁數也會），只取用得到的欄位
        return Edition.objects.filter(slug__isnull=False).only(*_SITEMAP_FIELDS).order_by("id")

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse("games:edition-detail", kwargs={"slug": obj.slug})


class EditionFlowchartSitemap(Sitemap):
    """
    Flowchart 分頁的獨立 URL（/games/<slug>/flowchart/）。

    分頁本身對所有訪客一律可見（tab 按鈕在 template 裡不分身分渲染），但內容
    是否「薄」取決於匿名訪客看不看得到免費的圖：initial=False 的圖一律鎖住
    只顯示付費牆文案，initial=True 的入門圖才有機會產出文字版（見
    game.rag.flowchart.outline.to_outline）。只有真的組得出文字版大綱的版本
    才收錄，避免 sitemap 裡塞進一堆「只有付費牆」的頁面。

    只信任兩種確定的歸屬關係：
      1. chart.linked_editions（明確共用）
      2. chart.rulebook.edition（這個 edition 自己的規則書生出的圖）
    刻意不比照 EditionDetailView 的 priority 3/4（同遊戲其他 edition 的規則書
    當退路）——那條路徑挑哪本規則書要看使用者當下的語言與 QuerySet 排序，
    不是穩定、可重現的關係，sitemap 只收錄「確定會顯示」的頁面比收錄「碰運氣
    可能顯示」更重要。漏掉的極端案例（真的靠退路顯示內容的 edition）不影響
    這個 edition 的主頁仍會被收錄。
    """

    protocol = "https"
    changefreq = "weekly"
    priority = 0.6
    limit = 2000
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        from django.db.models import Prefetch

        from game.models import RulebookFlowchart
        from game.rag.flowchart.outline import to_outline

        # 只取判斷要用的欄位：不載入草稿 JSON 與 rulebook 全文
        charts = (
            RulebookFlowchart.objects.published()
            .filter(initial=True)
            .select_related("rulebook", "publication")
            .only("id", "rulebook_id", "rulebook__edition_id", "publication__content")
            .prefetch_related(Prefetch("linked_editions", queryset=Edition.objects.only("id")))
        )

        edition_ids = set()
        for chart in charts:
            # 與公開頁一致：看 reviewer 核准的快照，不看草稿
            effective = chart.publication.content
            if not effective or not to_outline(effective):
                continue
            edition_ids.update(e.id for e in chart.linked_editions.all())
            if chart.rulebook_id and chart.rulebook.edition_id:
                edition_ids.add(chart.rulebook.edition_id)

        return Edition.objects.filter(
            id__in=edition_ids, slug__isnull=False,
        ).only(*_SITEMAP_FIELDS).order_by("id")

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse("games:edition-detail-tab", kwargs={"slug": obj.slug, "tab": "flowchart"})
