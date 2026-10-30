from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    """固定頁面。優先度：首頁 > 搜尋/Feed 列表 > 條款類。"""

    # 站台一律走 HTTPS。不指定的話 sitemap 會沿用請求的 scheme，
    # 一旦反向代理的 header 沒設好就會產出 http:// 的網址。
    protocol = "https"

    changefreq = "weekly"
    i18n = True
    alternates = True
    x_default = True

    PRIORITIES = {
        "home": 1.0,
        "games:search": 0.9,
        "feed:list": 0.7,
        "faq": 0.5,
        "about": 0.4,
        "privacy": 0.2,
        "terms": 0.2,
    }

    def items(self):
        return list(self.PRIORITIES.keys())

    def priority(self, item):
        return self.PRIORITIES.get(item, 0.5)

    def location(self, item):
        return reverse(item)


class EnglishOnlySitemap(Sitemap):
    """只有英文版的固定頁面。

    這些頁在 i18n_patterns 底下，所以 /ja/… 之類的網址仍然解析得到，但內容是同一份
    英文，模板已經一律 canonical 回英文版。這裡跟著只提交英文網址 —— 送出非 canonical
    的網址不會被懲罰，但會在 Search Console 留下一堆「重複網頁」的噪音。

    哪天這些頁真的做了多語版本，把項目搬回 StaticViewSitemap.PRIORITIES 即可。
    """

    protocol = "https"
    changefreq = "yearly"
    priority = 0.3
    i18n = False

    def items(self):
        return ["principles"]

    def location(self, item):
        # i18n=False 不會切語言，這裡的 reverse 拿到的就是無前綴的英文網址。
        return reverse(item)
