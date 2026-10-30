from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from feed.models import Work


class WorkSitemap(Sitemap):
    """Feed 文章頁。文章是每天進的，changefreq 用 daily。"""

    # 站台一律走 HTTPS。不指定的話 sitemap 會沿用請求的 scheme，
    # 一旦反向代理的 header 沒設好就會產出 http:// 的網址。
    protocol = "https"

    changefreq = "daily"
    priority = 0.5
    limit = 2000
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        # i18n=True 時 Django 會把整個 queryset 展開成 list 再分頁（index 算頁數也會），
        # 所以一定要 .only()：不取 content（整篇文章 HTML），否則每次都把整張表的全文載進 worker。
        return Work.objects.only("id", "publishdate").order_by("-publishdate", "id")

    def lastmod(self, obj):
        return obj.publishdate

    def location(self, obj):
        return reverse("feed:detail", kwargs={"pk": obj.pk})
