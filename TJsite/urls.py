
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.contrib.sitemaps import views as sitemap_views
from django.urls import path, include
from django.views.decorators.cache import cache_page
from django.views.generic import TemplateView, RedirectView
from feed.views import FetchRssView
from django.conf import settings
from django.conf.urls.static import static
from .admin import feed_panel, AdminStatsView, ErrorAlertAckView
from feed.sitemaps import WorkSitemap
from game.legacy_views import LegacyEditionRedirect
from game.sitemaps import EditionFlowchartSitemap, EditionSitemap
from game.views.original_views import EditionDetailView
from home.sitemaps import EnglishOnlySitemap, StaticViewSitemap
from home.views import AboutView, FaqView, LlmsTxtView, RobotsView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.http import FileResponse
import os

SITEMAPS = {
    'static': StaticViewSitemap,
    'static-en': EnglishOnlySitemap,
    'games': EditionSitemap,
    'games-flowchart': EditionFlowchartSitemap,
    'feeds': WorkSitemap,
}

def app_ads_txt(request):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_path = os.path.join(base_dir, "app-ads.txt")
    return FileResponse(open(file_path, "rb"), content_type="text/plain")

# ─────────────────────────────────────────────────────────────
# 路由分成三區，順序有意義：
#   1. /api/ 與後台 —— 機器讀的，永遠不加語言前綴
#   2. 舊網址 301 —— 已被搜尋引擎收錄的路徑，導到新的正規網址
#   3. 網頁路由 —— 給人看的 HTML，Phase 3 會包進 i18n_patterns
# ─────────────────────────────────────────────────────────────

urlpatterns = [
    # ── JSON API ──
    path('api/v1/', include('game.api_urls')),          # 新 App 的入口
    path('api/translation/', include('translation.urls')),
    path('api/feed/', include('feed.urls')),
    path('api/members/', include('member.urls')),
    path('api/stats/', include('stats.urls')),
    path('api/game/', include('game.urls')),
    path('api/msg/', include('msg.urls')),
    path('api/messaging/', include('messaging.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('interaction/', include('interaction.urls')),
    path('commerce/', include('commerce.urls')),
    path('acct/', include('allauth.urls')),

    # ── 後台 ──
    path('feed_panel/', feed_panel.urls),
    path('power/fetch_rss/', FetchRssView.as_view()),
    path('power/AdminStatsView/', AdminStatsView.as_view(), name='admin_stats'),
    path('power/error-ack/', ErrorAlertAckView.as_view(), name='admin_error_ack'),
    path('power/', admin.site.urls),
    path('tablejourney/', include('tablejourney.urls')),

    # ── SEO 端點（不加語言前綴）──
    path('robots.txt', RobotsView.as_view(), name='robots'),
    path('llms.txt', LlmsTxtView.as_view(), name='llms-txt'),
    # index 也要快取：它為了算每個 section 有幾頁，會跑一次各 section 的 _items()，
    # 等於每被抓一次就把所有 section 全表載入一次（曾讓 VPS worker 漲到 600MB+ 被 OOM）。
    path('sitemap.xml', cache_page(60 * 60 * 6)(sitemap_views.index), {
        'sitemaps': SITEMAPS,
        'sitemap_url_name': 'sitemap-section',
    }, name='sitemap-index'),
    # i18n=True 會掃全表 × 6 種語言，很貴；gunicorn 每個 worker 各快取一份就夠。
    path('sitemap-<section>.xml', cache_page(60 * 60 * 6)(sitemap_views.sitemap), {
        'sitemaps': SITEMAPS,
    }, name='sitemap-section'),

    # ── 靜態檔 ──
    path("app-ads.txt", app_ads_txt),

    # ── 舊網址 301 ──
    # /game/ 曾經和 /api/game/ 掛同一份 urlconf（造成 reverse() 解析到 /api/game/），
    # 現在只留這兩條明確的重導。
    path('game/search/', RedirectView.as_view(
        pattern_name='games:search', permanent=True, query_string=True)),
    path('game/edition/<uuid:pk>/', LegacyEditionRedirect.as_view()),
    # /game/<slug>/（單數）是 /games/<slug>/ 之前的網址，仍被搜尋引擎收錄。
    # 直接掛 EditionDetailView 而不是寫新的 redirect：它的 get() 本來就會在
    # request.path != canonical 時發 301，get_object() 也已經處理舊 slug 與裸 UUID，
    # 查不到就正常 404。必須排在上面兩條之後，否則 <str:slug> 會把 'search' 吃掉。
    path('game/<str:slug>/', EditionDetailView.as_view()),
    # /feed/ 是舊 WordPress 站的 RSS 路徑，現在的清單頁是 /feeds/
    path('feed/', RedirectView.as_view(pattern_name='feed:list', permanent=True)),

    # 舊的語言網址（無結尾斜線）。'jp' 是國家碼不是語言碼，正確的是 'ja'。
    path('en', RedirectView.as_view(pattern_name='home', permanent=True)),
    path('jp', RedirectView.as_view(url='/ja/', permanent=True)),
]

# ── 網頁路由：加語言前綴 ──
# prefix_default_language=False → 英文維持在 /、/games/…，其他語言是 /ja/games/…。
# 這段一定要在上面的 /api/ 之後才附加，否則 API 網址會被套上語言前綴而全部 404。
urlpatterns += i18n_patterns(
    path('', include('home.urls')),
    path('', include('game.web_urls')),
    path('', include('feed.web_urls')),
    path('', include('member.web_urls')),
    path('', include('interaction.web_urls')),
    path('about/', AboutView.as_view(), name='about'),
    path('privacy/', TemplateView.as_view(template_name='privacy.html'), name='privacy'),
    path('terms/', TemplateView.as_view(template_name='terms.html'), name='terms'),
    # Organization.publishingPrinciples 指向這頁（見 game/structured_data.py）
    path('principles/', TemplateView.as_view(template_name='principles.html'), name='principles'),
    path('faq/', FaqView.as_view(), name='faq'),
    path('removedata/', TemplateView.as_view(template_name='removedata.html')),
    prefix_default_language=False,
)

if settings.DEBUG:  # 只有在開發模式下才提供 media 檔案
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
