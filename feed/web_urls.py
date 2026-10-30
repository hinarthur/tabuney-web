# feed/web_urls.py
from django.urls import path
from feed.web_views import feed_page, feed_detail_page

app_name = 'feed'  # 設定 namespace

urlpatterns = [
    path('feeds/', feed_page, name='list'),
    path('feeds/<int:pk>/', feed_detail_page, name='detail'),
]