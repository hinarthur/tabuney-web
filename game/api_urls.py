"""
/api/v1/ 路由。新的 App 端點請加在這裡，不要再往 game/urls.py 加。
"""

from django.urls import path

from game.api_views import EditionDetailAPIView, EditionSearchAPIView

app_name = "game-api-v1"

urlpatterns = [
    path("games/", EditionSearchAPIView.as_view(), name="search"),
    path("games/<uuid:pk>/", EditionDetailAPIView.as_view(), name="detail"),
]
