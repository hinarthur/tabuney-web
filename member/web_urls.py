"""
member 的網頁路由（給人看的 HTML）。JSON 端點留在 member/urls.py 的 /api/members/。

注意 Google OAuth callback 沒有搬過來 —— static/js/auth.js 硬編碼了
/api/members/login/google/callback/，且該網址已註冊在 Google Console，動不得。
"""

from django.urls import path

from member.views import (
    EditionUnlockPickView,
    EditionUnlockReleaseView,
    MembershipCancelView,
    MembershipSuccessView,
    MembershipView,
)

app_name = "account"

urlpatterns = [
    path("membership/", MembershipView.as_view(), name="membership"),
    path("membership/success/", MembershipSuccessView.as_view(), name="membership-success"),
    path("membership/cancel/", MembershipCancelView.as_view(), name="membership-cancel"),
    # 免費名額的選取／退回。US$1 加購走 commerce:create-edition-unlock-session。
    path("unlocks/pick/", EditionUnlockPickView.as_view(), name="unlock-pick"),
    path("unlocks/release/", EditionUnlockReleaseView.as_view(), name="unlock-release"),
]
