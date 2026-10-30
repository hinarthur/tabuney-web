import ipaddress
import json
import socket
import time
from urllib.parse import urljoin, urlparse

import requests
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

from game.models import Edition, FlowchartSuggestion, GameSuggestion, RulebookFlowchart
from translation.selectors import get_translation

_validate_url = URLValidator(schemes=["http", "https"])


def _t(request, key, default):
    return get_translation(getattr(request, "lang", "en"), key, default)


# ---------------------------------------------------------------------------
# Rulebook URL 檢查
# ---------------------------------------------------------------------------
# 策略：只在「有明確證據」時才擋下 —— 網域解不到、404、或一般站台明擺著回 HTML。
# 其餘一律放行（BGG 之類的 bot 防護會回 403、Google Drive/Dropbox 分享連結一定是
# HTML 落地頁，這些都驗不出來但連結本身通常是對的），標成 unverified 交給人工審核。
#
# 會員給的 URL 是由 server 主動連出去抓，所以要防 SSRF：只允許 http/https，
# 而且每一次 redirect 的目標主機都要重新檢查，不能解到內網位址。SSRF 是唯一
# 「驗不出來也要擋」的情況，不放行。

# (連線, 讀取) 各自的上限，再加一個跨 redirect 的總時限 —— 不然最壞情況是
# 每一跳都卡滿，整個表單送出會拖到 web server 把 request 砍掉。
RULEBOOK_FETCH_TIMEOUT = (5, 5)
RULEBOOK_TOTAL_DEADLINE = 15  # 秒
RULEBOOK_MAX_REDIRECTS = 5
# 抓前 1KB 來看檔頭就夠判斷是不是 PDF，不必把整本規則書拉下來。
RULEBOOK_SNIFF_BYTES = 1024
_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/acrobat"}
# 這些 content-type 代表「伺服器自己也沒說清楚」，改用檔頭判斷。
_AMBIGUOUS_CONTENT_TYPES = {"application/octet-stream", "binary/octet-stream", ""}
_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TableJourneyBot/1.0)",
    "Accept": "application/pdf,*/*",
}

# 雲端硬碟／檔案分享服務：分享連結指向的是一頁 HTML 檢視器，抓不到 PDF 本體，
# 但連結本身很可能是對的。這些網域直接跳過內容檢查，交給人工開來看。
_FILE_SHARING_HOSTS = (
    "drive.google.com", "docs.google.com", "drive.usercontent.google.com",
    "dropbox.com", "dropboxusercontent.com",
    "onedrive.live.com", "1drv.ms", "sharepoint.com",
    "box.com", "mega.nz", "icloud.com",
    "wetransfer.com", "we.tl", "mediafire.com",
    # BGG 的檔案區與本站都掛在 Cloudflare 後面，機器人請求一律 403
    "boardgamegeek.com", "geekdo.com",
)

# 這些狀態碼代表「伺服器不讓我們看」，不代表連結是壞的（bot 防護、要登入、
# 不吃 GET/Range、限流、對方暫時掛掉），一律當作驗不出來而非失效。
_INCONCLUSIVE_STATUSES = {401, 403, 405, 406, 409, 429}

# 檢查結果
CHECK_OK = "ok"                    # 確認是 PDF
CHECK_UNVERIFIED = "unverified"    # 驗不出來 —— 放行，標記待人工確認
CHECK_UNREACHABLE = "unreachable"  # 明確失效 —— 擋下
CHECK_NOT_PDF = "not-pdf"          # 明確不是 PDF —— 擋下
CHECK_BLOCKED = "blocked"          # 指向內網／不該連的位址 —— 擋下


def _is_public_host(hostname: str) -> bool:
    """主機名稱解析出來的位址是否全部都是對外可路由的位址。"""
    if not hostname:
        return False
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            return False
    return True


def _is_file_sharing_host(hostname: str) -> bool:
    hostname = (hostname or "").lower()
    return any(
        hostname == h or hostname.endswith("." + h) for h in _FILE_SHARING_HOSTS
    )


def _host_resolves(hostname: str) -> bool:
    try:
        socket.getaddrinfo(hostname, None)
        return True
    except socket.gaierror:
        return False


def _fetch_rulebook_head(url: str):
    """手動跟著 redirect 走，逐跳擋掉內網位址，回傳 (verdict, response)。

    verdict 為 CHECK_OK 時 response 是最後一跳的 stream response（呼叫端負責關閉）；
    其餘 verdict 的 response 為 None。
    """
    session = requests.Session()
    current = url
    deadline = time.monotonic() + RULEBOOK_TOTAL_DEADLINE
    for _ in range(RULEBOOK_MAX_REDIRECTS + 1):
        parsed = urlparse(current)
        if parsed.scheme not in ("http", "https"):
            return CHECK_BLOCKED, None
        if not _is_public_host(parsed.hostname):
            # 分不出是「網域不存在」還是「解到內網」—— 前者是壞連結，後者是 SSRF。
            return (
                CHECK_BLOCKED if _host_resolves(parsed.hostname) else CHECK_UNREACHABLE
            ), None
        if time.monotonic() >= deadline:
            # 對方太慢不代表連結是壞的，交給人工開來看
            return CHECK_UNVERIFIED, None
        try:
            resp = session.get(
                current,
                headers={**_FETCH_HEADERS, "Range": f"bytes=0-{RULEBOOK_SNIFF_BYTES - 1}"},
                timeout=RULEBOOK_FETCH_TIMEOUT,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException:
            # 連線被拒、TLS 失敗、逾時…都可能只是我們這端連不出去
            return CHECK_UNVERIFIED, None

        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                return CHECK_UNVERIFIED, None
            current = urljoin(current, location)
            continue
        return CHECK_OK, resp

    # redirect 繞不完（多半是導向迴圈），當作驗不出來
    return CHECK_UNVERIFIED, None


def _check_rulebook_url(url: str) -> str:
    """檢查 URL 連得上而且指向 PDF，回傳上面的 CHECK_* 之一。"""
    hostname = urlparse(url).hostname
    sharing_host = _is_file_sharing_host(hostname)

    verdict, resp = _fetch_rulebook_head(url)
    if resp is None:
        if verdict == CHECK_UNREACHABLE and sharing_host:
            # 短網址服務（1drv.ms 之類）偶爾解不到，不當成壞連結
            return CHECK_UNVERIFIED
        return verdict

    try:
        if resp.status_code in _INCONCLUSIVE_STATUSES or resp.status_code >= 500:
            return CHECK_UNVERIFIED
        if resp.status_code >= 400:
            # 404/410 這類才是真的沒有這個檔
            return CHECK_UNVERIFIED if sharing_host else CHECK_UNREACHABLE

        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type in _PDF_CONTENT_TYPES:
            return CHECK_OK
        if sharing_host:
            # 分享連結回 HTML 檢視器是正常的，不代表裡面不是 PDF
            return CHECK_UNVERIFIED
        if content_type not in _AMBIGUOUS_CONTENT_TYPES:
            # 一般站台明確說了是別的東西（多半是 HTML 落地頁），不用再看檔頭
            return CHECK_NOT_PDF

        # content-type 不可靠時看 PDF 檔頭；有些站台會在 %PDF- 前補幾個位元組。
        try:
            head = next(resp.iter_content(chunk_size=RULEBOOK_SNIFF_BYTES), b"")
        except requests.RequestException:
            return CHECK_UNVERIFIED
        return CHECK_OK if b"%PDF-" in head[:RULEBOOK_SNIFF_BYTES] else CHECK_NOT_PDF
    finally:
        resp.close()


@method_decorator(csrf_protect, name="dispatch")
class GameSuggestionCreateView(View):
    """
    讓已登入會員推薦新增桌遊，存成待審核的 GameSuggestion。
    不直接建立 Game/Edition/Rulebook —— 由 staff 在 admin 人工審核後才手動建立正式資料。
    """

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "login_required"}, status=401)

        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            payload = request.POST

        name = (payload.get("name") or "").strip()
        rulebook_url = (payload.get("rulebook_url") or "").strip()
        url_check = CHECK_UNVERIFIED
        barcode = (payload.get("barcode") or "").strip()
        note = (payload.get("note") or "").strip()

        errors = {}
        if not name:
            errors["name"] = _t(request, "game.suggest.error.name-required", "Please enter the game name")
        if not rulebook_url:
            errors["rulebook_url"] = _t(request, "game.suggest.error.rulebook_url-required", "Please enter the rulebook URL")
        else:
            try:
                _validate_url(rulebook_url)
            except ValidationError:
                errors["rulebook_url"] = _t(request, "game.suggest.error.rulebook_url-invalid", "Invalid URL format")
            else:
                url_check = _check_rulebook_url(rulebook_url)
                if url_check in (CHECK_UNREACHABLE, CHECK_BLOCKED):
                    errors["rulebook_url"] = _t(
                        request, "game.suggest.error.rulebook_url-unreachable",
                        "We couldn't open this URL. Please check the link.",
                    )
                elif url_check == CHECK_NOT_PDF:
                    errors["rulebook_url"] = _t(
                        request, "game.suggest.error.rulebook_url-not-pdf",
                        "This link is not a PDF. Please link directly to the rulebook PDF file.",
                    )

        if errors:
            return JsonResponse({"success": False, "errors": errors}, status=400)

        submitted_by = getattr(request.user, "member", None)
        GameSuggestion.objects.create(
            name=name,
            rulebook_url=rulebook_url,
            barcode=barcode,
            note=note,
            submitted_by=submitted_by,
            rulebook_url_verified=(url_check == CHECK_OK),
        )

        return JsonResponse({
            "success": True,
            "message": _t(request, "game.suggest.modal.success", "Thanks for the suggestion! We'll review it soon."),
        })


# 一則建議的字數上限。夠寫完一段具體描述，又不至於讓人把整本規則書貼進來。
SUGGESTION_MAX_LENGTH = 2000


@method_decorator(csrf_protect, name="dispatch")
def _member_unlocked_flowchart(member, flowchart) -> bool:
    """這位會員有沒有永久解鎖「這張圖會出現在其上」的任何一款 edition。

    一張圖可能透過兩種途徑掛在 edition 上：自己 rulebook 所屬的 edition，
    或被直接標記共用（linked_editions）。兩種都算，與 _flowchart_context
    收集圖的方式一致。
    """
    unlocked = member.unlocked_edition_ids()
    if not unlocked:
        return False
    own = getattr(flowchart.rulebook, "edition_id", None)
    if own is not None and own in unlocked:
        return True
    return flowchart.linked_editions.filter(id__in=unlocked).exists()


class FlowchartSuggestionCreateView(View):
    """
    讓已登入會員對某張流程圖（以 flowchart_id 指定，即 edition 頁上選中的那個
    ruleset）留下改善建議，存成待審核的 FlowchartSuggestion。

    不直接改動流程圖 —— 由 staff 在 admin 讀過後人工調整。
    """

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "login_required"}, status=401)

        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            payload = request.POST

        flowchart_id = (payload.get("flowchart_id") or "").strip()
        edition_id = (payload.get("edition_id") or "").strip()
        content = (payload.get("content") or "").strip()

        if not content:
            return JsonResponse({"success": False, "errors": {"content": _t(
                request, "game.flowchart.suggest.error.empty",
                "Please write your suggestion",
            )}}, status=400)
        if len(content) > SUGGESTION_MAX_LENGTH:
            return JsonResponse({"success": False, "errors": {"content": _t(
                request, "game.flowchart.suggest.error.too-long",
                "Your suggestion is too long",
            )}}, status=400)

        try:
            flowchart = RulebookFlowchart.objects.published().get(id=flowchart_id)
        except (RulebookFlowchart.DoesNotExist, ValidationError, ValueError):
            # ValidationError/ValueError：flowchart_id 不是合法 UUID
            return JsonResponse({"success": False, "errors": {"flowchart": _t(
                request, "game.flowchart.suggest.error.generic",
                "Something went wrong. Please try again.",
            )}}, status=400)

        member = getattr(request.user, "member", None)

        # 非入門圖（initial=False）要看得到內容才該能對它留建議。放行條件與
        # EditionDetailView._flowchart_context 相同，是 OR 關係：
        #   1. tier feature 'flowchart_non_initial'
        #   2. 這張圖所屬的任一 edition 被這位會員永久解鎖（member.EditionUnlock）
        #
        # 第 2 點刻意不採信 payload 裡的 edition_id —— 那是客戶端給的，拿一個
        # 自己解鎖過的 edition 配上別人的 flowchart_id 就能繞過。改成從
        # flowchart 自己的歸屬（rulebook 的 edition + linked_editions）反推，
        # 與解鎖集合取交集。
        if not flowchart.initial and not (
            member and (
                member.can('flowchart_non_initial')
                or _member_unlocked_flowchart(member, flowchart)
            )
        ):
            return JsonResponse({"error": "subscription_required"}, status=403)

        edition = None
        if edition_id:
            edition = Edition.objects.filter(id=edition_id).first()

        FlowchartSuggestion.objects.create(
            flowchart=flowchart,
            edition=edition,
            ruleset=flowchart.ruleset,
            content=content,
            submitted_by=member,
        )

        return JsonResponse({
            "success": True,
            "message": _t(
                request, "game.flowchart.suggest.success",
                "Thanks! We'll take your suggestion into account.",
            ),
        })
