# translation/middleware.py
"""
語言判斷。分兩層：

  LocalePathMiddleware —— 從網址前綴啟動 Django 的語言，讓 reverse()/{% url %}
                          自動帶上正確前綴。
  LanguageMiddleware   —— 設定 request.lang，這是 {% t %} 與 API serializer
                          唯一的語言真相來源。

網頁與 API 的差別只在「語言從哪裡來」，不在後面的邏輯：
  網頁  → 網址前綴決定（/ja/games/x/ 是日文，/games/x/ 是英文）
  API   → ?lang= 或 session 決定（App 沒有網址前綴可用）
"""

from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.utils import translation

SUPPORTED_LANGS = {code for code, _ in settings.LANGUAGES}
DEFAULT_LANG = settings.LANGUAGE_CODE

# 這些前綴不參與 i18n_patterns，語言得走 query param / session
UNPREFIXED_PATHS = (
    '/api/', '/power/', '/acct/', '/static/', '/media/', '/commerce/',
    '/interaction/', '/feed_panel/', '/tablejourney/', '/sitemap', '/robots.txt',
)


class LocalePathMiddleware(LocaleMiddleware):
    """
    網址路徑是決定語言的唯一輸入。

    Django 原生的 LocaleMiddleware 還會看 django_language cookie 與 Accept-Language。
    在 prefix_default_language=False 之下那會造成：未加前綴的英文網址，對德文瀏覽器
    回德文 —— 同一個網址兩種語言，正是我們要消滅的重複內容。拿掉 cookie 與
    Accept-Language 的嗅探，網址與語言才是一對一。
    """

    def process_request(self, request):
        lang = translation.get_language_from_path(request.path_info) or settings.LANGUAGE_CODE
        translation.activate(lang)
        request.LANGUAGE_CODE = translation.get_language()

    def process_response(self, request, response):
        response.setdefault('Content-Language', translation.get_language())
        translation.deactivate()
        return response


class LanguageMiddleware:
    """設定 request.lang。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        query_lang = request.GET.get('lang')

        if request.path_info.startswith(UNPREFIXED_PATHS):
            # API / 後台：沿用原本的 ?lang= → session → 預設
            if query_lang in SUPPORTED_LANGS:
                request.session['lang'] = query_lang
            lang = request.session.get('lang', DEFAULT_LANG)
        else:
            # 網頁：網址前綴說了算。session 不得覆蓋網址，否則會出現
            # 「Googlebot 在英文網址拿到德文頁」這種經典的重複內容 bug。
            lang = translation.get_language()
            if lang not in SUPPORTED_LANGS:
                lang = DEFAULT_LANG
            # 舊的 ?lang= 連結仍然可用，canonical 會指向正規的前綴網址
            if query_lang in SUPPORTED_LANGS:
                lang = query_lang

        request.lang = lang
        return self.get_response(request)
