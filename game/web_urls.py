"""
game 的網頁路由（給人看的 HTML）。JSON 端點在 game/api_urls.py 與 game/urls.py。

`<str:slug>` 不能寫成 `<slug:slug>` —— Django 內建的 slug converter 只吃 ASCII，
會讓中日文 slug（例如 /games/鐵道任務-2013/）全部 404。這條路由同時接受
slug、舊 slug 與裸 UUID，由 EditionDetailView.get_object 解析，非正規的形式發 301。
"""

from django.urls import path

from game.views.original_views import (
    EditionDetailView,
    GameAutocompleteView,
    GameSearchView,
)
from game.views.suggestion_views import (
    FlowchartSuggestionCreateView,
    GameSuggestionCreateView,
)

app_name = "games"

urlpatterns = [
    path("games/", GameSearchView.as_view(), name="search"),
    path("games/suggest/", GameSuggestionCreateView.as_view(), name="suggest-game"),
    # 搜尋框的即時建議（AJAX GET）。跟下面的 flowchart/suggest 一樣，
    # 必須排在 <str:slug> 之前，否則會被 games/<slug>/ 當成一款遊戲吃掉。
    path(
        "games/autocomplete/",
        GameAutocompleteView.as_view(),
        name="autocomplete",
    ),
    # 流程圖改善建議（AJAX POST）。必須排在 <str:slug> 之前，否則會被
    # games/<slug>/ 吃掉。
    path(
        "games/flowchart/suggest/",
        FlowchartSuggestionCreateView.as_view(),
        name="suggest-flowchart",
    ),
    path("games/<str:slug>/", EditionDetailView.as_view(), name="edition-detail"),
    # 分頁深連結（flowchart/script），例如 /games/catan/flowchart/。rulesbot
    # 是預設分頁，沿用上面無後綴的網址，不在這裡加 tab 值。
    path("games/<str:slug>/<str:tab>/", EditionDetailView.as_view(), name="edition-detail-tab"),
]
