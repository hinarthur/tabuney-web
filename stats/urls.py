# stats/urls.py
#
# 掛在 /api/stats/ 底下的埋點端點。統計「讀」的那一側不在這裡——聚合結果由
# stats/reports.py 算好，經 TJsite/admin.py 的 AdminStatsView 送到 admin 首頁。
from django.urls import path

from .views import LanguageClickView

urlpatterns = [
    path('lang_click/', LanguageClickView.as_view(), name='lang-click'),
]
