"""
SEO 用的 template context：正規網址、各語言版本的網址。

hreflang_alternates 同時被兩個地方用，兩者要的網址形式不同，所以每筆同時給：
  1. base.html 的 <link rel="alternate" hreflang="..."> —— 用絕對網址 alt.url，
     搜尋引擎要靠它認出跨語言的對應關係
  2. 導覽列的語言切換器 —— 用相對路徑 alt.path，切語言只換語言、不換 host。
     絕對網址在這裡是錯的：SITE_URL 在 DEBUG 下寫死 http://localhost:8000，
     從區網另一台機器（192.168.x.x:8000）瀏覽時，一點語言就被丟去那台機器
     自己的 localhost。正式站也一樣，切語言不該有跨網域的能力。
"""

from django.conf import settings
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils import translation

from game.structured_data import organization_jsonld, webpage_jsonld, website_jsonld
from translation.selectors import get_translation

# 語言選單上的顯示名稱
LANGUAGE_LABELS = {
    'en': 'English',
    'zh': '華文',
    'ja': '日本語',
    'de': 'Deutsch',
    'fr': 'Français',
    'es': 'Español',
}

# seo.default.description 翻譯字串查無資料時的備援（含 "board game" 關鍵字）
DEFAULT_DESCRIPTION = (
    'Look up any board game: player count, playtime, setup, rules Q&A, '
    'flowcharts and ready-to-read game master scripts.'
)


def seo(request):
    site = settings.SITE_URL
    canonical = site + request.path

    alternates = []
    x_default = site + '/'

    match = getattr(request, 'resolver_match', None)
    # /api/ 之類不參與 i18n_patterns 的路徑沒有語言版本可列
    if match and not request.path.startswith('/api/'):
        for code, _ in settings.LANGUAGES:
            with translation.override(code):
                try:
                    url = reverse(match.view_name, args=match.args, kwargs=match.kwargs)
                except NoReverseMatch:
                    continue
            alternates.append({
                'code': code,
                'label': LANGUAGE_LABELS.get(code, code.upper()),
                'url': site + url,   # <link rel="alternate"> 用
                'path': url,         # 導覽列語言切換器用（同源相對路徑）
            })
            if code == settings.LANGUAGE_CODE:
                x_default = site + url

    lang = getattr(request, 'lang', settings.LANGUAGE_CODE)
    description = get_translation(lang, 'seo.default.description', DEFAULT_DESCRIPTION)
    logo_url = site + static('img/favicon/apple-icon-180x180.png')

    # Organization 是全站唯一的節點，它引用的網址不該隨當前語言浮動，
    # 所以這些 reverse 固定用預設語言解析。
    with translation.override(settings.LANGUAGE_CODE):
        contact_url = site + reverse('about') + '#contact'
        principles_url = site + reverse('principles')

    return {
        'SITE_URL': site,
        'canonical_url': canonical,
        'hreflang_alternates': alternates,
        'hreflang_x_default': x_default,
        # principles 頁只有英文版，它自己用這個值覆寫 canonical（見 principles.html）。
        # 與 Organization.publishingPrinciples 共用同一個值，兩邊不會漂開。
        'principles_url': principles_url,
        # 每頁都有的三個節點。頁面自己的節點由 view 放進 jsonld_nodes，
        # 兩份清單在 base.html 的 {% jsonld_graph %} 合併成單一 @graph
        # （@id 相同時後者勝，view 因此能覆寫這裡的預設節點）。
        'jsonld_base_nodes': [
            organization_jsonld(
                site, logo_url, description,
                contact_url=contact_url, principles_url=principles_url,
            ),
            website_jsonld(site),
            webpage_jsonld(site, canonical),
        ],
    }
