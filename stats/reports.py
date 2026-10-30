"""
搜尋行為的聚合報表。

刻意寫成不依賴 request 的純函式：目前由 TJsite/admin.py 的 AdminStatsView 呼叫、
渲染在 admin 首頁，日後首頁改版或改用其他前端都能直接沿用同一份。

除非特別註明，所有查詢都排除 is_bot=True。
"""

import hashlib
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db.models import Count, Max, Sum
from django.utils import timezone

from TJsite.context_processors import LANGUAGE_LABELS

from .models import (
    SearchLog, PageVisit, LanguageClick, ErrorLog, ErrorAlertAck, ServerSample,
)


def _humans(days):
    """指定天數內、非爬蟲的搜尋。"""
    since = timezone.now() - timedelta(days=days)
    return SearchLog.objects.filter(is_bot=False, created_at__gte=since)


def _rank(qs, limit, extra_values=()):
    """依關鍵字分組排名，附上最後一次搜尋時間。"""
    return list(
        qs.values('keyword', *extra_values)
        .annotate(total=Count('id'), last_at=Max('created_at'))
        .order_by('-total', '-last_at')[:limit]
    )


def search_insights(days=30, limit=30):
    """
    回傳 admin 首頁要的四塊資料。

    重點是 missing / missing_barcodes：那就是「有人找過、但站上沒有」的作品清單。
    result_count 為 null 的舊資料不算未命中（那是未知，不是零）。
    """
    qs = _humans(days)
    total = qs.count()

    missing_qs = qs.filter(result_count=0)
    missing_total = missing_qs.count()

    # matched_by 分佈；空字串是本欄位上線前的舊資料
    matched_by = list(
        qs.exclude(matched_by='')
        .values('matched_by')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    summary = {
        'days': days,
        'total': total,
        'missing_total': missing_total,
        'missing_rate': round(missing_total / total * 100, 1) if total else 0,
        # 不輸出 web/app 佔比：App 端數據已從首頁移除。SearchLog.source 仍照記，
        # 要看的時候從 admin 的 SearchLog 列表用 source 篩選即可。
        # 唯一一個不排除爬蟲的數字：拿來看雜訊有多少
        'bot_total': SearchLog.objects.filter(
            is_bot=True, created_at__gte=timezone.now() - timedelta(days=days)
        ).count(),
        'matched_by': matched_by,
    }

    return {
        'summary': summary,
        # 主角：該補哪些作品
        'missing': _rank(missing_qs, limit, extra_values=('input_kind',)),
        # 掃了條碼卻找不到 —— 條碼可直接反查是哪一款，優先處理
        'missing_barcodes': _rank(missing_qs.filter(input_kind='barcode'), limit),
        'top_keywords': _rank(qs.filter(result_count__gt=0), limit),
    }


def _daily_series(counts_by_date, start, days):
    """
    把 {date: count} 攤成連續 N 天的序列，缺資料的日子補 0，
    讓前端可以直接照日期畫出等長的折線圖，不用自己補洞。
    """
    return [
        {
            'date': (start + timedelta(days=i)).isoformat(),
            'count': counts_by_date.get(start + timedelta(days=i), 0),
        }
        for i in range(days)
    ]


def page_visit_insights(page, days=30):
    """近 N 天，指定頁面每天的到訪次數（含今天）。"""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    counts = {
        row['date']: row['count']
        for row in PageVisit.objects.filter(page=page, date__gte=start).values('date', 'count')
    }
    daily = _daily_series(counts, start, days)

    return {
        'summary': {
            'days': days,
            'total': sum(d['count'] for d in daily),
        },
        'daily': daily,
    }


# admin 首頁折線圖要比較的頁面，固定順序——前端照這個順序指定線的顏色，
# 順序本身就是色盲安全性的一部分（見 dataviz skill），改順序要連前端一起改。
TRACKED_PAGES = ('home', 'membership', 'game_search', 'about', 'feed_list')


def all_page_visit_insights(days=30):
    """一次算好 TRACKED_PAGES 每個頁面的到訪趨勢，key 是 page code，另外帶 label。"""
    labels = dict(PageVisit.PAGE_CHOICES)
    return {
        page: {'label': labels[page], **page_visit_insights(page, days=days)}
        for page in TRACKED_PAGES
    }


# admin 首頁語言點擊圖的折線順序，對齊 settings.LANGUAGES。跟 TRACKED_PAGES 一樣，
# 順序固定不循環——前端照這個順序指定線的顏色，順序本身就是色盲安全性的一部分，
# 改順序要連 templates/admin/index.html 的 --lc-* 色票一起改。
LANG_CLICK_ORDER = ('en', 'zh', 'ja', 'de', 'fr', 'es')


def language_click_insights(days=30):
    """
    近 N 天的語言切換點擊趨勢：每種介面語言各一條折線（langs），外加一組
    menu_open（點開頂 bar 語言選單的次數），前端拿它畫右軸的長條。

    語言名稱直接用 LANGUAGE_LABELS（和站上語言選單同一份），刻意維持原文、
    不接翻譯系統。
    """
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    # 一次撈完再於 Python 分組：資料量是 (種類 × 天數)，最多幾百列
    counts = {}
    for row in LanguageClick.objects.filter(date__gte=start).values(
        'kind', 'lang', 'date', 'count'
    ):
        counts.setdefault((row['kind'], row['lang']), {})[row['date']] = row['count']

    def series(kind, lang, label):
        daily = _daily_series(counts.get((kind, lang), {}), start, days)
        return {
            'label': label,
            'summary': {'days': days, 'total': sum(d['count'] for d in daily)},
            'daily': daily,
        }

    return {
        'days': days,
        'langs': {
            lang: series('select', lang, LANGUAGE_LABELS.get(lang, lang.upper()))
            for lang in LANG_CLICK_ORDER
        },
        'menu_open': series('menu_open', '', '點開語言選單'),
    }


# =============================
# 錯誤警示分級
# =============================
#
# ErrorLog 是「一天 × 一組錯誤」一列的聚合表，所以「今天又多了幾列」不是健康
# 指標：一個被 Google 索引到的舊網址，只要還有人點，每天都會準時生一列新的，
# 直到有人去做轉址為止。看列數只會天天緊張。
#
# 下面這組規則要回答的是另一個問題——「這裡面有哪幾件是我今天真的該動手的」。
# 判斷軸只有兩條：
#   1. 壞的是不是我們自己（站內連結、程式例外）→ 我們有能力也有責任修。
#   2. 有沒有打到真實使用者（member_count > 0）→ 有人被卡住了。
# 兩條都不中的，多半是外面的世界在敲門（舊網址、外站連錯、亂試網域），
# 那是網路噪音，不是故障。

# 5xx 只出現一兩次，通常是部署重啟那幾秒 nginx 打不到 gunicorn（502/503/504），
# 不是程式壞了。500 沒有這種解釋——那一定是 Python 丟了例外，所以 500 不吃門檻。
_ALERT_GATEWAY_MIN = 3
# 外站放的壞連結：一兩次可能只是有人手打錯網址，累積到這個量才值得做 301
_ALERT_EXTERNAL_MIN = 5
# 無來源的 404 量最大、價值最低（直接輸入、舊書籤、搜尋引擎索引），門檻拉最高
_ALERT_ORPHAN_MIN = 10

# 警示清單本身也要有上限，否則某天被灌爆時首頁會變成另一張長表
_ALERT_MAX = 30
# 篩站內 referer 前先撈的候選列數。不能直接用 limit：站內死連結的次數通常遠
# 低於外站噪音，只取前 30 名會全部被外站洗掉，反而漏掉最該修的那幾筆。
_ALERT_SCAN_DEPTH = 300


def _own_hosts():
    """
    本站自己的網域。referer 的 host 落在這裡面，就代表「是我們自己的頁面
    在放這條壞連結」——那是唯一一種我們改得動的 404。

    取自 ALLOWED_HOSTS 加 SITE_URL。ttoper.com 刻意不算站內（見 settings.py
    的註解：它由 nginx 301 掉，根本不會進 Django）。
    """
    hosts = set()
    for host in settings.ALLOWED_HOSTS:
        host = host.strip().lower().lstrip('*.')
        if host and host != '*':
            hosts.add(host)
    site_host = urlsplit(settings.SITE_URL).netloc.lower().split(':')[0]
    if site_host:
        hosts.add(site_host)
    return hosts


def _is_internal_referer(referer):
    """
    這個來源頁面是不是站內——也就是「我們自己有一頁在放這條壞連結」。

    光看 host 不夠。掃描器會把 Referer 直接設成目標網域（`https://tabuney.com`、
    `http://www.tabuney.com`），host 當然對得上，結果 /fetch、/proxy、/graphql/console
    這類探測全被算成站內死連結，把真正該修的那兩三筆淹掉。

    分辨的關鍵是 path：真實瀏覽器送的 Referer 一定帶 path，至少是 "/"（那是首頁）。
    裸網域不帶 path 是手工造出來的請求才有的樣子，一律不算站內。
    """
    if not referer:
        return False
    parts = urlsplit(referer)
    netloc = parts.netloc.lower()
    if not netloc:
        # 沒有 netloc 就只剩 path，那只可能是站內
        return bool(parts.path)
    if not parts.path:
        return False
    return netloc.split(':')[0] in _own_hosts()


def alert_ack_key(kind, path, referer=''):
    """一條錯誤警示的身分，對應 ErrorAlertAck.key。"""
    return hashlib.sha1(f'{kind}|{path}|{referer}'.encode()).hexdigest()


def error_insights(days=30, limit=30):
    """
    近 N 天使用者撞到的 HTTP 錯誤。

    最有價值的是 broken_links：referer 與 path 配成一組，直接指出「哪一頁在放
    哪條壞連結」。只看 path 只知道哪個網址壞了，修不了源頭。

    預設不把爬蟲算進總數（跟其他報表一致），但 bot_notfound 會另外報出來——
    爬蟲撞到的 404 通常代表站內某頁還留著舊連結，那是真的要修的東西。

    回傳的 alerts 是這支函式的重點：其餘欄位都是「發生了什麼」的原始資料，
    每天都會有新東西，看了也不知道要不要動；alerts 是「該動手的是哪幾件」，
    平常應該是空的。分級規則見檔案上方 _ALERT_* 常數旁的說明。
    """
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    qs = ErrorLog.objects.filter(date__gte=start)
    humans = qs.filter(is_bot=False)

    def _totals(queryset):
        row = queryset.aggregate(hits=Sum('count'), members=Sum('member_count'))
        return row['hits'] or 0, row['members'] or 0

    total, member_total = _totals(humans)
    notfound_total, _ = _totals(humans.filter(status_code=404))
    server_total, _ = _totals(humans.filter(status_code__gte=500))
    bot_notfound, _ = _totals(qs.filter(is_bot=True, status_code=404))

    def _rank_by(queryset, *fields, top=None):
        """依指定欄位分組，次數加總後排名。"""
        return [
            {
                **{f: row[f] for f in fields},
                'total': row['total'],
                'member_total': row['member_total'],
                'last_at': row['last_at'],
            }
            for row in queryset.values(*fields)
            .annotate(
                total=Sum('count'),
                member_total=Sum('member_count'),
                last_at=Max('last_seen_at'),
            )
            .order_by('-total', '-last_at')[:top or limit]
        ]

    def _status_breakdown(queryset):
        """
        把總數依狀態碼拆開。

        沒有這個的話，總數是唯一的線索：看到「錯誤 542 次｜404 104 次｜5xx 0 次」
        會以為剩下的 438 次憑空消失了，其實它們是 400/403，只是報表沒有出口。
        """
        return [
            {'status_code': row['status_code'], 'total': row['total']}
            for row in queryset.values('status_code')
            .annotate(total=Sum('count'))
            .order_by('-total')
        ]

    notfound = humans.filter(status_code=404)

    # ── 警示：這堆紀錄裡真正要動手的那幾件 ──────────────────────
    # 規則的理由見檔案上方 _ALERT_* 常數旁的說明。這裡只組資料，不做呈現。
    alerts = []
    # 已經被前面規則報過的 (狀態碼, path)，避免同一件事在清單裡出現兩次
    covered = set()

    def _add(level, kind, label, action, row, path='', referer='', note=''):
        alerts.append({
            'level': level,
            'kind': kind,
            'key': alert_ack_key(kind, path, referer),
            'label': label,
            'action': action,
            'path': path,
            'referer': referer,
            'note': note,
            'total': row['total'],
            'member_total': row['member_total'],
            'last_at': row['last_at'],
        })

    # 1. 伺服器錯誤。500 一次都算數；502/503/504 少量時多半是部署重啟的空窗，
    #    降級成提醒而不是警報，否則每次上線都會亮紅燈，久了就沒人看了。
    for row in _rank_by(
        humans.filter(status_code__gte=500), 'path', 'exception', 'status_code'
    ):
        code = row['status_code']
        if code == 500:
            _add('critical', 'server', '伺服器錯誤 500', '照例外訊息修程式',
                 row, path=row['path'], note=row['exception'] or '（沒抓到例外訊息）')
        elif row['total'] >= _ALERT_GATEWAY_MIN:
            _add('critical', 'server', f'後端連不上 {code}', '查 gunicorn／nginx 是否反覆重啟',
                 row, path=row['path'], note='連續發生，已經不像單次部署重啟')
        else:
            _add('warning', 'server', f'後端連不上 {code}', '通常不用處理',
                 row, path=row['path'], note='只出現幾次，多半是部署重啟那幾秒打不到後端')
        covered.add((code, row['path']))

    # 2. 站內死連結：我們自己的頁面上放著連不到的網址。這是唯一「一定是我們的錯、
    #    而且改得動」的 404，所以不設次數門檻，出現一次就報。
    #    刻意用 qs 而不是 humans——爬蟲撞到的站內死連結一樣是真的死連結（見
    #    ErrorLog 的 docstring），差別只在沒有真人被卡到。
    linked_404 = _rank_by(
        qs.filter(status_code=404).exclude(referer=''), 'referer', 'path',
        top=_ALERT_SCAN_DEPTH,
    )
    for row in linked_404:
        if not _is_internal_referer(row['referer']):
            continue
        _add('critical', 'internal_link', '站內死連結', '把來源頁面上的連結改掉或補上轉址',
             row, path=row['path'], referer=row['referer'])
        covered.add((404, row['path']))

    # 3. 會員撞到的其他錯誤。已登入代表是真實使用者不是掃描器，被卡住就是體驗
    #    出事了，即使 path 看起來沒問題也要知道。
    for row in _rank_by(humans.filter(member_count__gt=0), 'path', 'status_code'):
        code = row['status_code']
        if (code, row['path']) in covered:
            continue
        if code == 400:
            # 會員的 400 幾乎都是 DRF 的表單驗證沒過——那是功能正常運作的樣子，
            # 亮紅燈會讓真的紅燈失去意義。只有同一支端點爆量時才值得看一眼。
            if row['total'] < _ALERT_EXTERNAL_MIN:
                continue
            _add('warning', 'member', '會員的請求一直被擋下 400',
                 '多半是表單驗證沒過；量這麼大的話看看是不是前端送錯格式',
                 row, path=row['path'])
        else:
            _add('critical', 'member', f'會員撞到 {code}',
                 '照著這個網址自己走一次，看是哪裡把人帶過去的',
                 row, path=row['path'], note='已登入的人撞到，不是掃描器')
        covered.add((code, row['path']))

    # 4. 外站放的壞連結。修不了對方的頁面，但可以做 301 把流量接住，所以是
    #    「值得排進待辦」而不是「今天要修」。
    for row in linked_404:
        if _is_internal_referer(row['referer']):
            continue
        if row['total'] < _ALERT_EXTERNAL_MIN or (404, row['path']) in covered:
            continue
        _add('warning', 'external_link', '外站連到不存在的網址', '考慮做 301 把這些流量接住',
             row, path=row['path'], referer=row['referer'])

    # 5. 無來源的 404：舊書籤、搜尋引擎索引、手打網址。量最大價值最低，門檻最高。
    for row in _rank_by(notfound.filter(referer=''), 'path'):
        if row['total'] < _ALERT_ORPHAN_MIN or (404, row['path']) in covered:
            continue
        _add('warning', 'orphan', '舊網址持續被打', '考慮做 301，否則它每天都會出現在清單裡',
             row, path=row['path'], note='沒有來源頁面可追，多半是舊連結或書籤')

    # 已標記處理、而且標記之後沒再發生的，從清單拿掉。要在截斷之前做，
    # 否則被藏起來的那幾條會白白佔掉 _ALERT_MAX 的名額。
    acked_at = dict(
        ErrorAlertAck.objects.filter(key__in={a['key'] for a in alerts})
        .values_list('key', 'acked_at')
    )
    acked = 0
    visible = []
    for a in alerts:
        if a['key'] in acked_at and a['last_at'] <= acked_at[a['key']]:
            acked += 1
        else:
            visible.append(a)
    alerts = visible

    # critical 先排，同級內次數多的先排
    alerts.sort(key=lambda a: (a['level'] != 'critical', -a['total']))
    alerts = alerts[:_ALERT_MAX]

    return {
        # 首頁上唯一需要每天看的東西；其餘欄位都是查證用的原始資料
        'alerts': alerts,
        'alert_counts': {
            'critical': sum(1 for a in alerts if a['level'] == 'critical'),
            'warning': sum(1 for a in alerts if a['level'] == 'warning'),
            'acked': acked,
        },
        'summary': {
            'days': days,
            'total': total,
            'notfound_total': notfound_total,
            'server_total': server_total,
            'member_total': member_total,
            'bot_notfound': bot_notfound,
        },
        'by_status': _status_breakdown(humans),
        # 主角：哪一頁在放壞連結。排除 referer 空字串——那是直接輸入網址或來源
        # 被瀏覽器擋掉的，沒有「源頭頁面」可修。
        'broken_links': _rank_by(notfound.exclude(referer=''), 'referer', 'path'),
        # 沒有來源的 404：多半是舊網址被收藏／被搜尋引擎索引，看要不要做轉址
        'orphan_404': _rank_by(notfound.filter(referer=''), 'path'),
        # 伺服器出錯（5xx）：帶著例外訊息，這是要立刻修的
        'server_errors': _rank_by(
            humans.filter(status_code__gte=500), 'path', 'exception', 'status_code'
        ),
        # 400/403 原本只被算進 total，UI 上完全看不到。400 多半是 DisallowedHost
        # （有人拿不在 ALLOWED_HOSTS 的網域打進來），403 是權限或 CSRF，兩種都需要
        # 知道是打哪個 path，所以帶 status_code 一起分組。
        'client_errors': _rank_by(
            humans.filter(status_code__in=(400, 403)), 'path', 'status_code'
        ),
    }


# =============================
# VPS 負荷
# =============================

# 跟 deploy/vps/mem-snapshot.sh 的觸發條件同一組，兩邊的「紅燈」才會是同一件事
_SERVER_MEM_AVAIL_MIN_PCT = 15
_SERVER_SWAP_MAX_MB = 1200


def server_insights(days=7):
    """
    最新一筆 ServerSample，加上近 N 天每小時一點的走勢。

    降採樣取每小時「最差」的值（可用 RAM 取最小、swap 與 load 取最大）而不是平均：
    OOM 是瞬間的事，平均會把那根尖刺抹平，圖上就看不出曾經差點出事。
    """
    latest = ServerSample.objects.first()
    if latest is None:
        return {'latest': None, 'series': [], 'alerts': []}

    since = timezone.now() - timedelta(days=days)
    buckets = {}
    for s in ServerSample.objects.filter(created_at__gte=since).order_by('created_at'):
        hour = timezone.localtime(s.created_at).replace(minute=0, second=0, microsecond=0)
        b = buckets.get(hour)
        if b is None:
            buckets[hour] = {
                't': hour,
                'mem_available_mb': s.mem_available_mb,
                'swap_used_mb': s.swap_used_mb,
                'load5': s.load5,
            }
        else:
            b['mem_available_mb'] = min(b['mem_available_mb'], s.mem_available_mb)
            b['swap_used_mb'] = max(b['swap_used_mb'], s.swap_used_mb)
            b['load5'] = max(b['load5'], s.load5)

    alerts = []
    avail_pct = latest.mem_available_mb / latest.mem_total_mb * 100 if latest.mem_total_mb else 0
    if avail_pct < _SERVER_MEM_AVAIL_MIN_PCT:
        alerts.append(f'可用 RAM 只剩 {avail_pct:.0f}%（低於 {_SERVER_MEM_AVAIL_MIN_PCT}%）')
    if latest.swap_used_mb > _SERVER_SWAP_MAX_MB:
        alerts.append(f'swap 用了 {latest.swap_used_mb} MB（超過 {_SERVER_SWAP_MAX_MB} MB）')

    return {
        'latest': {
            'created_at': latest.created_at,
            'mem_total_mb': latest.mem_total_mb,
            'mem_available_mb': latest.mem_available_mb,
            'mem_available_pct': round(avail_pct, 1),
            'swap_used_mb': latest.swap_used_mb,
            'load1': latest.load1,
            'load5': latest.load5,
            'disk_used_pct': latest.disk_used_pct,
        },
        'series': list(buckets.values()),
        'alerts': alerts,
        'thresholds': {
            'mem_available_min_pct': _SERVER_MEM_AVAIL_MIN_PCT,
            'swap_max_mb': _SERVER_SWAP_MAX_MB,
        },
    }
