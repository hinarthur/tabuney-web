"""
讓本機 admin 首頁讀得到正式站的統計數字。

刻意不碰資料庫：拿 .env 裡的 VPS_API_USERNAME / VPS_API_PASSWORD 去正式站換 JWT，
再呼叫正式站自己那支 AdminStatsView，把 JSON 原封不動帶回來。因為完全沒有對正式站
開資料庫連線，「不會誤改到正式站」是結構上的保證，不是靠設定或紀律。

認證流程沿用 game/sync_service.py:452 的 _get_auth_token()，以及
translation/admin.py:85 的 allow_redirects=False（POST 被 302 會被轉成 GET）。
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = 'admin_stats_prod'
# 正式站那支 view 很慢：calc_avg_duration 會把所有 open/close 事件拉進 Python 迴圈
# 配對，反覆切換來源不該每次都重等一輪。
CACHE_TTL = 60


def fetch_prod_stats(force_refresh=False):
    """
    回傳 (data, error)。取得成功時 error 是 None；失敗時 data 是 None。

    一律不拋例外——這是 admin 首頁的附加功能，正式站連不上時該顯示訊息，
    而不是讓整個首頁掛掉。
    """
    if not force_refresh:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached, None

    username = settings.VPS_API_USERNAME
    password = settings.VPS_API_PASSWORD
    if not username or not password:
        return None, 'VPS_API_USERNAME / VPS_API_PASSWORD 未設定，無法登入正式站'

    base = settings.VPS_SYNC_BASE_URL.rstrip('/')

    try:
        auth_resp = requests.post(
            f'{base}/api/token/',
            json={'username': username, 'password': password},
            timeout=(10, 30),
            allow_redirects=False,  # 跟隨 301/302 會把 POST 變成 GET，帳密就丟了
        )

        if auth_resp.status_code in (301, 302, 307, 308):
            location = auth_resp.headers.get('Location', '(unknown)')
            return None, f'登入正式站被 redirect ({auth_resp.status_code}) 到 {location}'

        if auth_resp.status_code != 200:
            return None, f'登入正式站失敗 ({auth_resp.status_code})'

        access_token = auth_resp.json().get('access')
        if not access_token:
            return None, '登入正式站成功，但沒有拿到 access token'

        # 刻意不帶 source=prod：就算哪天 AdminStatsView 的環境守衛失效，
        # 正式站也只會回自己的本地資料，遞迴止於第一層。
        resp = requests.get(
            f'{base}/power/AdminStatsView/',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=(10, 60),
        )

        if resp.status_code == 403:
            return None, (
                f'正式站拒絕存取（403）：AdminStatsView 需要 is_staff，'
                f'請確認 {username} 這個帳號在正式站是管理員'
            )
        if resp.status_code != 200:
            return None, f'讀取正式站統計失敗 ({resp.status_code})'

        data = resp.json()
    except requests.RequestException as e:
        logger.exception('讀取正式站統計失敗')
        return None, f'連線正式站失敗：{e}'
    except ValueError as e:
        logger.exception('正式站回應不是合法 JSON')
        return None, f'正式站回應不是合法 JSON：{e}'

    cache.set(CACHE_KEY, data, CACHE_TTL)
    return data, None
