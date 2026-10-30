import hashlib
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import F
from django.utils import timezone
from datetime import timedelta
from .models import (
    ViewLog, SearchLog, PageVisit, PageVisitCooldown, LanguageClick, ErrorLog,
)
from member.models import Member

# 刻意不儲存原始 User-Agent，只留一個布林值：UA 字串本身可用於瀏覽器指紋。
_BOT_UA_MARKERS = (
    'bot', 'crawl', 'spider', 'slurp', 'bingpreview',
    'headless', 'python-requests', 'curl', 'wget',
)


def _get_member(request):
    """從 request 取得 Member，沒有就回傳 None"""
    if request.user.is_authenticated:
        try:
            return Member.objects.get(pk=request.user.pk)
        except Member.DoesNotExist:
            return None
    return None


def _is_bot_ua(request):
    """單純看 User-Agent 判斷是不是機器人。只回傳布林值，UA 不落地。"""
    ua = (request.META.get('HTTP_USER_AGENT') or '').lower()
    if not ua:
        return True
    return any(marker in ua for marker in _BOT_UA_MARKERS)


def _is_bot(request, keyword):
    """判斷這次搜尋是不是機器人打的。"""
    # 爬蟲會把 game/structured_data.py 的 JSON-LD 樣板字面（如 {search_term_string}）
    # 原封不動當關鍵字送出來，這種一定不是真人。
    if '{' in keyword:
        return True
    return _is_bot_ua(request)


def guess_input_kind(keyword):
    """由字串形狀推斷使用者輸入的是條碼還是文字（涵蓋 EAN-8 / UPC-A / EAN-13）。"""
    if keyword.isdigit() and 8 <= len(keyword) <= 14:
        return 'barcode'
    return 'text'


def log_view(request, obj, cooldown_minutes=30):
    """
    通用的瀏覽記錄函式，適用於任何 model。

    去重只對已登入會員生效（用 member 當鍵）。匿名訪客每次瀏覽都計一次 ——
    以前是靠 session.create() 發一個 sessionid 來去重，但那等於在不知情的訪客
    裝置上寫 cookie，ePrivacy 第 5(3) 條下需要同意（＝要彈窗）。寧可讓匿名的
    view_count 語意變成「頁面載入次數」，換取全站對訪客零 cookie。
    """
    ct = ContentType.objects.get_for_model(obj)
    member = _get_member(request)

    if member is not None:
        time_threshold = timezone.now() - timedelta(minutes=cooldown_minutes)
        recent = ViewLog.objects.filter(
            content_type=ct,
            object_id=obj.pk,
            member=member,
            created_at__gte=time_threshold,
        ).exists()
        if recent:
            return

    ViewLog.objects.create(
        content_type=ct,
        object_id=obj.pk,
        member=member,
    )
    # 更新快取欄位
    type(obj).objects.filter(pk=obj.pk).update(
        view_count=F('view_count') + 1
    )


def log_search(request, keyword, search_type, *, source,
               result_count=None, matched_by=''):
    """
    通用的搜尋記錄函式。請在搜尋做完之後才呼叫，才拿得到 result_count / matched_by。

    source 由呼叫端明講（'web' / 'app'），不從 request 猜。
    """
    keyword = keyword.strip()
    # 不記 session_key：已登入者用 member 串連就夠（還跨 session/裝置），
    # 匿名者不記任何識別碼。收一個用不到的識別碼只是純負債。
    SearchLog.objects.create(
        keyword=keyword,
        search_type=search_type,
        member=_get_member(request),
        result_count=result_count,
        matched_by=matched_by,
        input_kind=guess_input_kind(keyword),
        source=source,
        lang=getattr(request, 'lang', '') or '',
        is_bot=_is_bot(request, keyword),
    )


def log_page_visit(request, page, cooldown_minutes=30):
    """
    指定頁面的到訪計數，一天一列累加。`page` 必須是 PageVisit.PAGE_CHOICES 裡的值——
    刻意不 fallback：追蹤新頁面前要先去 models.py 登記，不要讓打錯字的頁面
    默默生出一組永遠對不到報表的資料。

    排除明顯的爬蟲 UA，不然折線圖會被爬蟲流量淹沒。去重只對已登入會員生效
    （跟 log_view 同一套邏輯，用 member 當鍵）：同一會員 30 分鐘內重複造訪
    同一頁面只算一次。匿名訪客沒有識別碼可去重，每次載入都計一次。
    """
    valid_pages = {choice for choice, _ in PageVisit.PAGE_CHOICES}
    if page not in valid_pages:
        raise ValueError(f"'{page}' 不在 PageVisit.PAGE_CHOICES 裡，先去 models.py 登記")

    if _is_bot_ua(request):
        return

    member = _get_member(request)
    if member is not None:
        now = timezone.now()
        cooldown, created = PageVisitCooldown.objects.get_or_create(
            page=page, member=member, defaults={'last_seen_at': now}
        )
        if not created:
            if cooldown.last_seen_at >= now - timedelta(minutes=cooldown_minutes):
                return
            cooldown.last_seen_at = now
            cooldown.save(update_fields=['last_seen_at'])

    today = timezone.localdate()
    PageVisit.objects.get_or_create(page=page, date=today)
    PageVisit.objects.filter(page=page, date=today).update(count=F('count') + 1)


def log_language_click(request, kind, lang=''):
    """
    語言切換的點擊計數，一天一列累加。kind 見 LanguageClick.KIND_CHOICES。

    `lang` 只接受 settings.LANGUAGES 那六碼——資料庫裡另有 it/ko/nl/pt 等 Tribe，
    但那些是內容語言、沒有介面翻譯（見 settings.py 的註解），不該混進這份統計。
    不合法的值一律丟 ValueError 交給呼叫端變成 400，不 fallback：這支是公開端點，
    默默吞掉錯誤只會生出一堆對不到報表的資料。

    排除明顯的爬蟲 UA。不做任何去重（理由見 LanguageClick 的 docstring）。
    """
    valid_kinds = {choice for choice, _ in LanguageClick.KIND_CHOICES}
    if kind not in valid_kinds:
        raise ValueError(f"'{kind}' 不在 LanguageClick.KIND_CHOICES 裡")

    if kind == 'select':
        if lang not in dict(settings.LANGUAGES):
            raise ValueError(f"'{lang}' 不是介面語言（見 settings.LANGUAGES）")
    else:
        # menu_open 沒有語言可言，強制正規化成空字串，unique_together 才不會被繞過
        lang = ''

    if _is_bot_ua(request):
        return

    today = timezone.localdate()
    LanguageClick.objects.get_or_create(kind=kind, lang=lang, date=today)
    LanguageClick.objects.filter(kind=kind, lang=lang, date=today).update(
        count=F('count') + 1
    )


# =============================
# HTTP 錯誤記錄
# =============================

# 只記這些狀態碼。刻意不寫成「>= 400 全記」：401 是 API 未帶 token 的日常回應、
# 405/406 多半是掃描器亂打，記了只是噪音。要加新的狀態碼在這裡加。
ERROR_TRACKED_STATUSES = (400, 403, 404, 500, 502, 503, 504)

# 這些前綴不記：靜態檔與媒體檔的 404 由 nginx / whitenoise 處理，混進來會把
# 「使用者撞到壞連結」的訊號淹掉。
# ads.txt / sellers.json / llms.txt 是廣告與 AI 爬蟲的網路慣例檔：站上沒有就是沒有，
# crawler 會固定來要，那不是壞連結。/.well-known/ 整個目錄同理。
_ERROR_SKIP_PREFIXES = (
    '/static/', '/media/', '/favicon.ico', '/apple-touch-icon',
    '/ads.txt', '/sellers.json', '/llms.txt', '/.well-known/',
)

# 掃描器特徵。這類 path 一天可以生出上千種變形，全部落地就等於讓別人替我們
# 灌資料庫。直接丟掉，連 is_bot=True 都不記。
#
# 這些掃描器送的是正常瀏覽器 UA，_is_bot_ua() 抓不到，不在這裡擋就會被當成
# 「真人撞到的 404」，把報表整個淹掉——舊網域 ttoper.com 指向同一台機器，
# 全世界掃 WordPress 的 bot 都會打進來，wp-json 一條就佔掉大半。
_ERROR_SCAN_MARKERS = (
    '.php', '.asp', '.aspx', '.jsp', '.cgi', '.env', '.git', '.sql', '.bak',
    'wp-admin', 'wp-content', 'wp-includes', 'wp-login', 'wp-json', 'xmlrpc',
    '/wp/', 'wordpress', 'phpmyadmin', 'cgi-bin', '/vendor/',
    '/administrator/', 'magento', '/file-manager/',
    '.vscode', 'sftp-config', '/.aws', '/.ssh', '/.svn', '/.azure',
    '/actuator', '/telescope',
    '/backup/', '/old/', '/new/', '/blog/',
)

# 憑證外洩掃描：/config.yaml、/docker-compose.yml、/app/config.toml、/src/config.yaml…
# 用 endswith 而不是子字串——'.yml' 當子字串會誤殺任何含這三個字的 slug。
_ERROR_SCAN_SUFFIXES = ('.yml', '.yaml', '.toml', '.ini', '.conf', '.pem', '.key')

# 精確比對的掃描 path。這些字串太短，當子字串會誤殺未來真的做出來的路由；
# 精確比對就沒這問題——哪天真的開了 /mcp 端點，它會回 200，根本走不到這裡。
_ERROR_SCAN_PATHS = frozenset({
    '/mcp', '/mcp/', '/api/mcp', '/sse', '/sse/', '/jumbo', '/magento_version',
    # SSRF／open proxy 探測。這些會把 Referer 偽造成本站網域，不擋掉就會被
    # 報表算成「站內死連結」，把真正該修的那幾筆淹掉。
    '/fetch', '/fetch/', '/proxy', '/proxy/',
    '/graphql', '/graphql/', '/graphql/console',
    '/open', '/open/', '/open/visitors/info/gets',
})


def _clean_url(url, max_length=500):
    """
    去掉 query string 與 fragment。

    query string 常常夾帶個資（重設密碼 token、email、追蹤參數），錯誤報表完全
    用不到，所以在落地前就砍掉而不是事後清。站內 referer 只留 path，站外 referer
    留 scheme://host/path —— 外部來源是誰本身就是重點（別人的站在放我們的壞連結）。
    """
    if not url:
        return ''
    parts = urlsplit(url)
    if parts.netloc:
        cleaned = f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.scheme else f"//{parts.netloc}{parts.path}"
    else:
        cleaned = parts.path
    return cleaned[:max_length]


def _is_scan_path(path):
    """明顯是漏洞掃描的 path。"""
    lowered = path.lower()
    if lowered in _ERROR_SCAN_PATHS:
        return True
    if lowered.endswith(_ERROR_SCAN_SUFFIXES):
        return True
    return any(marker in lowered for marker in _ERROR_SCAN_MARKERS)


def _same_path(a, b):
    """
    兩個 path 指的是不是同一個東西（來源＝目的地的判斷用）。

    比對前先 percent-decode：掃描器會送 /%2eazure/credentials 這種編碼過的
    Referer，字面上跟 request.path 的 /.azure/credentials 不相等，直接比字串
    就會漏掉，那筆於是被當成「站內某頁連到 /.azure/credentials」——host 對得上，
    看起來就像我們自己的頁面在放這條連結。unquote 之後兩邊才對得起來。

    尾斜線也要一起正規化，理由是 APPEND_SLASH：有人打 /ja/games/...，Django
    先 301 到 /ja/games/.../ 才 404，Referer 卻還是原來那個沒斜線的。兩者差一個
    字元，看起來就成了「某頁連到它自己加斜線的版本」。真正的站內死連結不會長
    這樣，所以把這種配對一併視為來源＝目的地。
    """
    return unquote(a).rstrip('/') == unquote(b).rstrip('/')


def _error_fingerprint(status_code, path, referer, exception, is_bot):
    """
    這組錯誤的身分。unique_together 用它而不是直接用 path + referer，理由見
    ErrorLog 的 docstring（PostgreSQL B-tree 索引列有大小上限）。
    """
    raw = f"{status_code}|{path}|{referer}|{exception}|{int(is_bot)}"
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()


def describe_exception(exc):
    """例外壓成一行：類別名稱 + 訊息開頭，夠分辨同一個 path 的不同壞法就好。"""
    if exc is None:
        return ''
    message = str(exc).replace('\n', ' ').strip()
    return f"{type(exc).__name__}: {message}"[:200] if message else type(exc).__name__[:200]


def log_error(request, status_code, exception=None):
    """
    記錄一次 HTTP 錯誤，一天一列累加。由 stats.middleware.ErrorLogMiddleware 呼叫。

    referer 是這張表存在的理由：它指出「哪一頁在放這條壞連結」。path 只說明
    哪個網址壞了，兩者要一起看才找得到源頭。

    爬蟲不排除只標記 is_bot：爬蟲撞到的 404 往往正是站內某頁留著舊連結沒清，
    這訊號有價值，只是報表預設不把它算進總數。真正的掃描器由 _is_scan_path()
    直接丟掉，不落地。

    這支絕對不能讓請求失敗——記錄統計比不上把頁面回給使用者重要，所以整段
    包 try/except，出事就靜靜放棄這一筆。
    """
    if status_code not in ERROR_TRACKED_STATUSES:
        return

    path = request.path
    if path.startswith(_ERROR_SKIP_PREFIXES) or _is_scan_path(path):
        return

    try:
        raw_referer = request.META.get('HTTP_REFERER') or ''
        referer = _clean_url(raw_referer)
        # 掃描器會把 Referer 設成自己正在打的那個 URL（來源＝目的地），結果佔滿
        # 「哪一頁在放壞連結」那張主表。真正的壞連結幾乎不會來源等於目的地，
        # 所以清掉 referer 讓它落到「無來源的 404」，而不是整筆丟掉——path 本身
        # 仍可能有價值。
        if raw_referer and _same_path(urlsplit(raw_referer).path, request.path):
            referer = ''
        exc_text = describe_exception(exception)
        is_bot = _is_bot_ua(request)
        # 這支 middleware 掛在 AuthenticationMiddleware 外層，遇到在它之前就被
        # 擋掉的請求時 request.user 根本還沒被設上去，所以用 getattr 取。
        user = getattr(request, 'user', None)
        is_member = bool(user and user.is_authenticated)

        path = _clean_url(path)
        fingerprint = _error_fingerprint(status_code, path, referer, exc_text, is_bot)
        today = timezone.localdate()

        ErrorLog.objects.get_or_create(
            fingerprint=fingerprint,
            date=today,
            defaults={
                'status_code': status_code,
                'path': path,
                'referer': referer,
                'exception': exc_text,
                'is_bot': is_bot,
                'last_seen_at': timezone.now(),
            },
        )
        # 用 F() 更新而非讀出來改：同一個壞連結可能被多個 worker 同時撞到
        ErrorLog.objects.filter(fingerprint=fingerprint, date=today).update(
            count=F('count') + 1,
            member_count=F('member_count') + (1 if is_member else 0),
            last_seen_at=timezone.now(),
        )
    except Exception:
        # 統計壞掉不該連累使用者的請求；這裡本來就是在處理錯誤回應的路徑上，
        # 再拋一個例外只會把 500 頁面也弄壞。
        pass
