from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .utils import log_language_click


class LanguageClickView(APIView):
    """
    頂 bar 語言切換的埋點：POST {"kind": "menu_open"} 或 {"kind": "select", "lang": "ja"}。

    authentication_classes = [] 是刻意的：這支端點不需要知道你是誰，拿掉
    SessionAuthentication 之後 (1) 不會觸發 DRF 的 CSRF 檢查——匿名訪客本來就沒有
    csrftoken cookie 可帶，(2) 保證這條路徑永遠不讀寫 session，維持站上對訪客零
    cookie 的原則。寫進去的也只是一個 (kind, lang, 日期) 的計數，不含任何識別碼。
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        try:
            log_language_click(
                request,
                kind=request.data.get('kind') or '',
                lang=request.data.get('lang') or '',
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)
