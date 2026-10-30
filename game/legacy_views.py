"""
舊網址的 301 重導。

/api/game/edition/<uuid>/ 與 /game/edition/<uuid>/ 曾經是遊戲詳細頁的公開網址，
已被搜尋引擎收錄。它們現在無條件導向 /games/<slug>/，把權重收斂到單一 URL。

舊版 App（1.3.1）也打這兩條路徑要 JSON，經確認可以直接失效；新 App 請改用
GET /api/v1/games/<uuid>/。
"""

from django.http import Http404, HttpResponsePermanentRedirect
from django.views import View

from game.models import Edition


class LegacyEditionRedirect(View):
    """把舊的 UUID 網址導到正規 slug 網址，保留 query string。"""

    def get(self, request, pk):
        edition = Edition.objects.filter(pk=pk).only("id", "slug").first()
        if edition is None:
            raise Http404("No Edition matches the given query.")

        target = edition.get_absolute_url()
        query_string = request.META.get("QUERY_STRING")
        if query_string:
            target = f"{target}?{query_string}"
        return HttpResponsePermanentRedirect(target)
