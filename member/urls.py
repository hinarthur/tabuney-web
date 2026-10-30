# member/urls.py
#
# 掛在 /api/members/ 底下的 JSON 端點。給人看的 HTML 頁面（方案頁、付款結果頁）
# 已搬到 member/web_urls.py 的 /membership/，這裡只留 301。
from django.urls import path
from django.views.generic import RedirectView
from .views import (
    GoogleLoginView, GoogleLoginCallbackView, GoogleLoginStartView,
    MemberDetailView, ActivityTrackView, LogoutView
)

urlpatterns = [
    # App 用：POST id_token / access_token 換 JWT。介面不可變動，已上架版本在用。
    path('login/google/', GoogleLoginView.as_view(), name='google-login'),
    # 網頁用：authorization code flow 的起點
    path('login/google/start/', GoogleLoginStartView.as_view(), name='google-login-start'),
    # 這一支不能搬：已註冊在 Google Console
    path('login/google/callback/', GoogleLoginCallbackView.as_view(), name='google-login-callback'),
    path('me/', MemberDetailView.as_view(), name='member-detail'),
    path('activity_track/', ActivityTrackView.as_view(), name='activity_track'),
    path('logout/', LogoutView.as_view(), name='logout'),

    # ─── 舊的公開網址：已搬到 /membership/，一律 301 ───
    path('membership/success/', RedirectView.as_view(
        pattern_name='account:membership-success', permanent=True), name='membership_success'),
    path('membership/cancel/', RedirectView.as_view(
        pattern_name='account:membership-cancel', permanent=True), name='membership_cancel'),
    path('membership/', RedirectView.as_view(
        pattern_name='account:membership', permanent=True), name='membership'),
]