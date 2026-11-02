"""
匿名也能送出的回饋端點共用的防護。

站方原則是匿名訪客零 cookie（不記 IP、不記 session_key），所以這裡的每一道防護
都不能依賴「認出是誰」：
  * CSRF 只對已登入者檢查 —— 匿名請求沒有可冒用的身分，而要求 csrftoken 等於逼
    瀏覽器先拿一個 cookie
  * 灌水靠 honeypot 欄位、簽章 token（最短填寫時間）、「全站匿名總量」上限、
    重複內容偵測，計數器與指紋本身都不帶任何識別碼
"""

import hashlib
import time
from functools import wraps

from django.core import signing
from django.core.cache import cache
from django.views.decorators.csrf import csrf_protect

# 前端表單放一個藏起來的欄位，真人看不到也不會填；有值的就是機器人。
HONEYPOT_FIELD = "website"

# 全站匿名送出的每分鐘上限。是總量不是每人：沒有識別碼就沒有「每人」可言。
# 正常流量遠低於此，到頂通常代表有人在灌，寧可暫時擋掉匿名送出。
ANON_SUBMISSIONS_PER_MINUTE = 30
ANON_SUBMISSIONS_PER_HOUR = 300

# 已登入者每小時最多送幾份（用 DB 計，見 views）
MEMBER_SUBMISSIONS_PER_HOUR = 10

# 簽章 token：載入問卷（GET）時發，送出（POST）時帶回。
# 不是 cookie、不存伺服器，所以匿名訪客仍然零 cookie；伺服器只驗簽章與時間。
#   * 發出後不到 MIN_FILL_SECONDS 就送出 → 不是真人填的（機器人不先 GET 或秒送）
#   * 超過 TOKEN_MAX_AGE → 頁面開太久，請使用者重新整理
#   * 同一顆 token 最多用 TOKEN_MAX_USES 次（中途離開補送 + 正式送出，正常最多 2 次）
TOKEN_SALT = "feedback.survey.token"
MIN_FILL_SECONDS = 3
TOKEN_MAX_AGE = 6 * 3600
TOKEN_MAX_USES = 5

# 同樣內容十分鐘內只收一次
DUPLICATE_WINDOW = 600


def csrf_if_authenticated(view_func):
    """
    已登入 → 照 Django 預設檢查 CSRF；匿名 → 不檢查。

    回傳的 view 標記為 csrf_exempt，讓 CsrfViewMiddleware 放行，改由這裡決定。
    用在 class-based view 時寫成 method_decorator(csrf_if_authenticated, name="dispatch")。
    """
    protected = csrf_protect(view_func)

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated:
            return protected(request, *args, **kwargs)
        return view_func(request, *args, **kwargs)

    _wrapped.csrf_exempt = True
    return _wrapped


def is_honeypot_filled(payload) -> bool:
    return bool((payload.get(HONEYPOT_FIELD) or "").strip())


def anon_quota_exceeded() -> bool:
    """
    記一筆匿名送出，回傳是否已超過本分鐘的全站上限。

    快取是 FileBasedCache，incr 不是原子操作，多個 worker 同時寫會少算幾筆；
    這只是防灌水的粗略閘門，不需要精確。
    """
    now = int(time.time())
    per_minute = _bump(f"feedback:anon:{now // 60}", 120)
    per_hour = _bump(f"feedback:anon-h:{now // 3600}", 3700)
    return per_minute > ANON_SUBMISSIONS_PER_MINUTE or per_hour > ANON_SUBMISSIONS_PER_HOUR


def issue_token(survey_id) -> str:
    return signing.dumps({"s": survey_id, "t": int(time.time())}, salt=TOKEN_SALT, compress=True)


def check_token(token, survey_id) -> str:
    """回傳 "ok" | "invalid" | "too_fast" | "expired"。"""
    if not isinstance(token, str) or not token:
        return "invalid"
    try:
        data = signing.loads(token, salt=TOKEN_SALT)
        if data["s"] != survey_id:
            return "invalid"
        age = time.time() - data["t"]
    except (signing.BadSignature, KeyError, TypeError):
        return "invalid"
    if age < MIN_FILL_SECONDS:
        return "too_fast"
    if age > TOKEN_MAX_AGE:
        return "expired"
    return "ok"


def _bump(key, timeout) -> int:
    if cache.add(key, 1, timeout=timeout):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)
        return 1


def token_overused(token) -> bool:
    key = "feedback:tok:" + hashlib.sha256(token.encode()).hexdigest()[:32]
    return _bump(key, TOKEN_MAX_AGE + 60) > TOKEN_MAX_USES


def is_duplicate_submission(fingerprint: str) -> bool:
    """同樣的內容十分鐘內第二次出現 → True。指紋是內容的雜湊，不含任何訪客識別。"""
    key = "feedback:dup:" + hashlib.sha256(fingerprint.encode()).hexdigest()[:32]
    return not cache.add(key, 1, timeout=DUPLICATE_WINDOW)
