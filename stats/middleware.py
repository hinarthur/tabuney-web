"""
把使用者撞到的 HTTP 錯誤記進 ErrorLog。

放在 MIDDLEWARE 的最外層（第一個），才看得到所有回應——包含路由完全沒中的
404、以及其他 middleware 自己回的錯誤。放在中間的話那些請求根本不會經過這裡。
"""

from .utils import describe_exception, log_error


class ErrorLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # process_exception 已經記過的就不要再記一次：例外被 Django 轉成 500
        # 回應之後還是會流回這裡，不擋掉的話同一次錯誤會被計兩次。
        if response.status_code >= 400 and not getattr(request, '_error_logged', False):
            request._error_logged = True
            log_error(request, response.status_code)

        return response

    def process_exception(self, request, exception):
        """
        未處理的例外。這裡記是為了拿到例外類別與訊息——等它變成 500 回應之後
        就只剩一個狀態碼，看不出是哪裡壞的。

        回傳 None 讓 Django 照原本的流程繼續處理（該噴 500 就噴 500），這支
        middleware 只旁聽、不改變行為。

        注意 Http404 也會走到這裡：Django 之後會把它轉成 404 回應，所以狀態碼
        要照它的類型分流，不能一律當 500。
        """
        from django.http import Http404
        from django.core.exceptions import PermissionDenied

        if isinstance(exception, Http404):
            status_code = 404
        elif isinstance(exception, PermissionDenied):
            status_code = 403
        else:
            status_code = 500

        request._error_logged = True
        # Http404 / PermissionDenied 是正常的流程控制，不是「壞掉」，不留例外訊息
        # （而且 Http404 的訊息常常直接夾帶查無此物的 id，沒有保存價值）
        exc = exception if status_code == 500 else None
        log_error(request, status_code, exception=exc)
        return None
