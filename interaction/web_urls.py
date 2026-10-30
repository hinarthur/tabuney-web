"""
interaction 的網頁路由（給人看的 HTML）。

update-interaction 留在 interaction/urls.py —— 它是 JS 驅動的 POST，沒有 SEO 價值，
不加語言前綴才能讓 {% url %} 的輸出保持穩定。
"""

from django.urls import path

from interaction.views import CollectionView

app_name = "collection"

urlpatterns = [
    path("my/collection/", CollectionView.as_view(), name="index"),
]
