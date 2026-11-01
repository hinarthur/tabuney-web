"""Beta 模式總開關（settings.BETA_MODE）的唯一讀取入口。

beta 期間所有付費閘門一律放行、付費 UI 一律隱藏。呼叫端寫成
`is_beta() or <原本的權限判斷>`，不要改動原本的判斷式——關掉開關就要原樣恢復。
"""
from functools import wraps

from django.conf import settings
from django.shortcuts import redirect


def is_beta() -> bool:
    return bool(getattr(settings, "BETA_MODE", False))


def beta_closed(view_func):
    """beta 期間關閉的頁面／動作（membership 頁、結帳、解鎖選取）：一律導回首頁。

    UI 入口已經藏起來了，這層是給直接打網址或舊分頁送出的表單。放在
    login_required 外層，未登入者也是直接回首頁而不是先被要求登入。
    Stripe webhook 不要套：beta 前建立的 session 仍要能入帳。
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if is_beta():
            return redirect("home")
        return view_func(request, *args, **kwargs)
    return _wrapped
