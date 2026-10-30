from django.urls import path
from django.views.generic import RedirectView
from .views import update_interaction

urlpatterns = [
    # JS 驅動的 POST，不加語言前綴，{% url %} 輸出才穩定
    path("update-interaction/", update_interaction, name="update-interaction"),

    # 舊的公開網址：收藏頁已搬到 /my/collection/
    path("collection/", RedirectView.as_view(
        pattern_name="collection:index", permanent=True, query_string=True), name="collection"),
]
