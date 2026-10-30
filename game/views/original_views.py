import logging
import random
import uuid

from django.conf import settings
from django.core.paginator import Paginator
from django.http import Http404, HttpResponsePermanentRedirect, JsonResponse
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import TemplateView

from game.models import Edition
from game.selectors import (
    AUTOCOMPLETE_MIN_CHARS, annotate_editions, annotate_member_interactions,
    autocomplete_editions, browse_editions_page, search_editions,
)
from stats.utils import log_search, log_page_visit

logger = logging.getLogger(__name__)


class GameAutocompleteView(View):
    """
    搜尋框的即時建議端點 GET /games/autocomplete/?q=xx，回傳最多 8 筆 JSON。

    刻意不重用 GameSearchView 的 ajax 分支：那條路會跑 annotate_editions +
    annotate_member_interactions，再 prefetch rulebooks/roles__entity 並渲染整份
    卡片模板 —— 一次要 200ms 以上。建議清單只需要名稱、網址、縮圖三個欄位。

    這裡刻意不呼叫 log_search()。每次鍵入都記的話，打一次「catan」就會在
    SearchLog 灌進四列半成品關鍵字，熱門關鍵字統計會整個失真；理由與
    GameSearchView 中「載入更多不記 log」那段相同 —— 一次搜尋只該留一列。
    真正的那一列由使用者送出表單時的 GameSearchView 負責寫。

    同理不記 IP 也不碰 session：匿名訪客在這裡不留任何識別碼。
    """

    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        results = [
            {
                'name': e.name,
                'url': e.get_absolute_url(),
                # thumbnail 是 blank=True 的 ImageField，空字串時取 .url 會炸
                'thumbnail': e.thumbnail.url if e.thumbnail else '',
            }
            for e in autocomplete_editions(query)
        ]
        return JsonResponse({'results': results})


class GameSearchView(TemplateView):
    """
    網站的搜尋 / 瀏覽頁。查詢與標註邏輯在 game/selectors.py，與 /api/v1/ 共用。
    無查詢時是全量瀏覽清單，依 browse_editions_page() 的分值排序。
    App 的 JSON 搜尋請用 GET /api/v1/games/。
    """

    template_name = "game/game_search.html"
    PAGE_SIZE = 20

    def _annotate(self, editions):
        """卡片要的所有衍生欄位：全站共用的徽章 + 當前會員自己的收藏／喜好。"""
        return annotate_member_interactions(
            annotate_editions(editions),
            getattr(self.request.user, 'member', None),
        )

    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # 網站的「載入更多」：回傳算好的卡片 HTML 片段。搜尋與瀏覽兩種狀態共用同一份契約。
        if is_ajax:
            try:
                page = max(int(request.GET.get('page', 1)), 1)
            except (TypeError, ValueError):
                page = 1

            if query:
                # 「載入更多」刻意不記 log：一次搜尋只該留一列，否則熱門關鍵字會被翻頁次數灌水
                paginator = Paginator(search_editions(query).editions, self.PAGE_SIZE)
                pg = paginator.get_page(page)
                editions, has_next = list(pg.object_list), pg.has_next()
            else:
                editions, has_next = browse_editions_page(
                    (page - 1) * self.PAGE_SIZE, self.PAGE_SIZE,
                    request.GET.get('seed', ''),
                )

            html = render_to_string(
                'game/partials/game_cards.html',
                {'results': self._annotate(editions)},
                request=request,
            )
            return JsonResponse({
                'html': html,
                'has_next': has_next,
                'next_page': page + 1 if has_next else None,
            })

        # 只計整頁載入，「載入更多」的 ajax 分頁請求（上面那個分支）不算，
        # 理由跟下面 log_search 略過分頁一樣：一次到訪只該留一筆。
        log_page_visit(request, 'game_search')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get('q', '').strip()

        # 前端的 debounce 門檻直接讀這個值，不要在 JS 裡另外寫死一份 —— 兩邊
        # 一旦飄開，會變成前端不送、後端卻願意回答（或反過來）的詭異狀態。
        context['autocomplete_min_chars'] = AUTOCOMPLETE_MIN_CHARS

        if not query:
            # seed 要寫進 DOM 讓後續「載入更多」帶回來，前 30 名的洗牌才可重現
            seed = str(random.randrange(2 ** 31))
            editions, has_next = browse_editions_page(0, self.PAGE_SIZE, seed)

            context['results'] = self._annotate(editions)
            context['browse_seed'] = seed
            context['has_next'] = has_next
            context['total_count'] = Edition.objects.count()
        else:
            result = search_editions(query)
            total_count = result.editions.count()
            log_search(
                self.request, query, 'edition', source='web',
                result_count=total_count, matched_by=result.matched_by,
            )
            paginator = Paginator(result.editions, self.PAGE_SIZE)
            pg = paginator.get_page(1)
            results_list = self._annotate(list(pg.object_list))

            context['results'] = results_list
            context['query'] = query
            context['total_count'] = total_count
            context['has_next'] = pg.has_next()

        # 只有無查詢的落地頁掛 SearchAction，搜尋結果頁是 noindex 的。
        # 這裡覆寫 context processor 那個不帶 SearchAction 的 WebSite 節點（@id 相同）。
        if not query:
            from django.urls import reverse
            from game.structured_data import website_jsonld
            context['jsonld_nodes'] = [
                website_jsonld(settings.SITE_URL, reverse('games:search')),
            ]

        return context

from django.views.generic import DetailView
from translation.models import Tribe
from stats.utils import log_view

class EditionDetailView(DetailView):
    """
    網站的版本詳細頁 /games/<slug>/。
    JSON 版在 GET /api/v1/games/<uuid>/，兩者共用 selectors 與 serializers。
    """

    model = Edition
    template_name = "game/edition_detail.html"
    context_object_name = "edition"

    # 深連結用的分頁 slug。"info" 是預設分頁，網址本身不帶後綴，但 /info/ 收在
    # DEFAULT_TAB_ALIASES 裡，舊網址與手動打後綴的人 301 收斂回無後綴網址，而不是
    # 404。Rulesbot 的網址後綴是 /chat/；/rulesbot/ 是它的別名，301 到 /chat/。
    DEFAULT_TAB = "info"
    TAB_SLUGS = {"flowchart", "script", "chat"}
    DEFAULT_TAB_ALIASES = {"info"}
    TAB_SLUG_ALIASES = {"rulesbot": "chat"}

    # 四個分頁各自是獨立頁面：只建構自己那頁的 context、只渲染自己那頁的面板，
    # 另外三個分頁的內容完全不進 DOM。四個網址因此輸出真正不同的內容，而不是
    # 同一份 HTML 換一個 active class（那對搜尋引擎與 AI 回答引擎是重複內容，
    # 也讓每一頁都要付出所有分頁的查詢成本）。
    #
    # 刻意不拆成四個 view class：URL 只有一條 games/<slug>/<tab>/，tab 是 kwarg，
    # 而 context_processors 的 hreflang 與 game/sitemaps.py 都靠
    # reverse('games:edition-detail-tab', kwargs={'slug':…, 'tab':…})。把 tab 寫死
    # 進 path 會同時打壞那兩處。get_object()/get() 的 slug→UUID→alias 解析與 301
    # 收斂也只該有一份（還被 TJsite/urls.py 的舊網址共用）。
    #
    # tab → (template, context builder, 標題後綴的翻譯 key)
    TAB_CONFIG = {
        "chat": ("game/edition_detail_rulesbot.html", "_rulesbot_context", "game.chat.h2_suffix"),
        "flowchart": ("game/edition_detail_flowchart.html", "_flowchart_context", "game.flowchart.h2_suffix"),
        "script": ("game/edition_detail_script.html", "_script_context", "game.script.h2_suffix"),
        "info": ("game/edition_detail_info.html", "_info_context", "game.info.h2_suffix"),
    }

    def current_tab(self):
        # tab 可能不存在（無後綴網址，以及 TJsite/urls.py 那條沒有 tab kwarg 的
        # 舊路由 /game/<slug>/），一律當成預設的 info 分頁。
        return self.kwargs.get("tab") or self.DEFAULT_TAB

    def get_template_names(self):
        return [self.TAB_CONFIG[self.current_tab()][0]]

    def get_object(self, queryset=None):
        """
        依序嘗試 slug → 裸 UUID → 舊 slug（EditionSlugAlias）。

        UUID 分支讓舊書籤與 /api/game/edition/<uuid>/ 的重導共用同一份查詢；
        alias 分支讓改過名的版本發 301 而不是 404。
        """
        if getattr(self, "_object", None) is not None:
            return self._object

        ident = self.kwargs.get("slug") or str(self.kwargs.get("pk") or "")
        qs = queryset if queryset is not None else self.get_queryset()

        obj = qs.filter(slug=ident).first()

        if obj is None:
            try:
                obj = qs.filter(pk=uuid.UUID(ident)).first()
            except (ValueError, AttributeError, TypeError):
                obj = None

        if obj is None:
            from game.models import EditionSlugAlias
            alias = EditionSlugAlias.objects.filter(slug=ident).select_related("edition").first()
            if alias is None:
                raise Http404("No Edition matches the given query.")
            obj = alias.edition

        self._object = obj
        return obj

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        tab = kwargs.get("tab")
        if tab in self.DEFAULT_TAB_ALIASES:
            tab = None  # /info/ 收斂回無後綴網址
        elif tab in self.TAB_SLUG_ALIASES:
            tab = self.TAB_SLUG_ALIASES[tab]  # /rulesbot/ 收斂到 /chat/
        elif tab is not None and tab not in self.TAB_SLUGS:
            raise Http404("Unknown tab.")
        # 用舊 slug、裸 UUID 或非規範 tab 後綴進來的，導到正規網址
        canonical = obj.get_absolute_url()
        if tab:
            canonical = f"{canonical}{tab}/"
        if request.path != canonical:
            query_string = request.META.get("QUERY_STRING")
            target = f"{canonical}?{query_string}" if query_string else canonical
            return HttpResponsePermanentRedirect(target)

        # Edition Access 付款完成後，Stripe 會把使用者導回 ?unlocked=1&session_id=…
        redirect_response = self._handle_unlock_return(request, obj)
        if redirect_response is not None:
            return redirect_response
        response = super().get(request, *args, **kwargs)
        if getattr(self, "_preview_chart", None) is not None:
            # 草稿預覽：不得被收錄，也不得被任何快取存下來給別人看
            response["X-Robots-Tag"] = "noindex, nofollow"
            response["Cache-Control"] = "private, no-store"
        return response

    def _handle_unlock_return(self, request, edition):
        """處理付款完成的回跳。回傳 redirect 或 None（None＝這不是回跳請求）。

        為什麼不能只信 webhook：webhook 依賴 Stripe 打得到我們（本機開發還要
        stripe listen 開著）。它沒到時，使用者付了錢、回到頁面卻什麼都沒變，
        而 ?unlocked=1 本身只代表「Stripe 說付完了、使用者回來了」，並不保證
        解鎖已經建立。所以這裡主動向 Stripe 確認並補發（冪等，與 webhook 共用
        同一組函式，誰先到都一樣），並明確告訴使用者結果。

        處理完一律 redirect 回乾淨的網址：重新整理不會重複顯示訊息，session_id
        也不會留在網址列、書籤或分享連結裡。
        """
        if request.GET.get("unlocked") != "1":
            return None

        from django.contrib import messages
        from django.http import HttpResponseRedirect

        member = self._member()
        if member is None:
            # 登入狀態掉了：沒有對象可以驗證，也不能憑網址發放，直接清掉參數
            return HttpResponseRedirect(request.path)

        from commerce.views import fulfil_edition_unlock_from_session
        from translation.models import Translation, Tribe

        granted = fulfil_edition_unlock_from_session(
            member, edition, request.GET.get("session_id", ""),
        )

        key = "game.unlock.success" if granted else "game.unlock.return.pending"
        try:
            tribe = Tribe.objects.get(language=self._interface_lang())
            text = Translation.objects.get(tribe=tribe, key=key).value
        except (Tribe.DoesNotExist, Translation.DoesNotExist):
            text = key
        (messages.success if granted else messages.warning)(request, text)

        return HttpResponseRedirect(request.path)

    def get_queryset(self):
        # game__affiliate / __artwork 已不在這裡 select_related：唯一的消費端是
        # _affiliate_context()，而它配對的 template 區塊目前整段是 {% comment %}。
        return super().get_queryset().select_related(
            'game',
            'language',
            'region',
            'msrp_currency'
        ).prefetch_related(
            'rulebooks',
            'rulebooks__language',
            'game__editions__rulebooks',
            'game__editions__rulebooks__language',
            'roles__entity'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        edition = self.object
        tab = self.current_tab()

        # 四個分頁現在真的是四個獨立頁面，所以四頁都記一次瀏覽。view_count 的語意
        # 因此是「頁面載入次數」——以前從 sitemap／搜尋直接落在 /flowchart/ 的流量
        # 完全不計（分頁切換是純前端 pushState），現在會算進來。已登入會員仍受
        # stats.log_view 的 30 分鐘 cooldown 保護，不受影響。
        log_view(self.request, edition)

        context['initial_tab'] = tab
        context['tab_h2_key'] = self.TAB_CONFIG[tab][2]

        from game.selectors import content_rulebooks_for, edition_tab_flags
        content_rulebooks = content_rulebooks_for(edition)

        # 只建構這一頁需要的東西。內容不存在時 builder 會 raise Http404。
        getattr(self, self.TAB_CONFIG[tab][1])(context, content_rulebooks)

        # 流程圖分頁的書本按鈕（rulesbot 分頁已在上面設好，不覆蓋）
        from game.selectors import rulebook_source_link
        context.setdefault('rulebook_source', rulebook_source_link(content_rulebooks))

        # 分頁列得知道另外幾個分頁存不存在，但那只要 EXISTS，不必跑完整建構。
        # 自己那頁的旗標由上面的完整建構寫死，setdefault 讓它優先：便宜檢查與完整
        # 建構萬一漂開，至少不會出現「頁面渲染得出來、自己那顆按鈕卻不見」。
        flags = edition_tab_flags(edition, content_rulebooks)
        context.setdefault('has_flowchart', flags.has_flowchart)
        context.setdefault('has_script', flags.has_script)

        # Edition Access 的狀態四個分頁都要（標題列右上角的 CTA 是共用的，見
        # edition_detail.html），所以放這裡而不是塞在某一頁的建構裡。排在分頁
        # 建構之後：內容不存在時上面已經 raise Http404，不必白算一次。
        self._add_unlock_context(context, edition)

        self._add_jsonld(context, tab)
        return context

    # ── 共用小工具 ────────────────────────────────────────────────────

    def _member(self):
        """目前使用者的 Member；未登入或查無資料回 None。

        同一個 request 內只查一次。各分頁現在除了自己那頁的建構之外，還都會再
        問一次 Member（標題列右上角共用的 Edition Access CTA），不快取的話每頁
        要多跑幾趟查詢；更麻煩的是每次拿到不同實例，Member 上的解鎖 id 快取
        （unlocked_edition_ids）會跟著失效，等於再多查幾次。
        """
        if hasattr(self, '_member_cache'):
            return self._member_cache

        member = None
        if self.request.user.is_authenticated:
            try:
                from member.models import Member
                member = Member.objects.get(id=self.request.user.id)
            except Member.DoesNotExist:
                member = None
        self._member_cache = member
        return member

    def _interface_lang(self):
        return getattr(self.request, "lang", "en")

    # ── 各分頁的 context ─────────────────────────────────────────────

    def _rulesbot_context(self, context, content_rulebooks):
        """Rulesbot 分頁 /games/<slug>/。"""
        edition = self.object
        user_lang_code = self.request.GET.get('lang') or self._interface_lang()

        # Chat Logic Status（就緒判準 = whole_context 非空，見 selectors）
        # 1. matched   — 這個版本自己就有就緒的規則書
        # 2. linked    — 同一款遊戲的其他版本有（chat 會借用，並在開場白標示出處）
        # 3. not_ready — 都沒有
        #
        # 刻意呼叫 chat API 用的同一個解析函式，而不是自己判一次：chat 實際餵給
        # 模型的是一整包規則書（同 edition 同語言的全部就緒規則書），頁面顯示的
        # 狀態要跟 chat 真正拿到的東西一致。
        from game.selectors import resolve_chat_bundle
        bundle = resolve_chat_bundle(edition, user_lang_code)

        edition_alt = None
        if bundle.rulebooks and bundle.status == "linked":
            edition_alt = bundle.source_edition

        context['chat_status'] = bundle.status
        context['edition_alt'] = edition_alt
        # 多份文件時開場白要交代這次問答涵蓋哪些，否則使用者看到 "Ref 2" 不知從何而來
        context['chat_bundle_titles'] = [rb.title for rb in bundle.rulebooks]
        # 書本按鈕：連到 chat 實際使用的規則書的出處
        from game.selectors import rulebook_source_link
        context['rulebook_source'] = rulebook_source_link(bundle.rulebooks)

        # staff 的模型覆寫 radio：只要這頁的 chat 是可用的就顯示
        context['whole_context_available'] = (
            self.request.user.is_authenticated
            and self.request.user.is_staff
            and bundle.status != "not_ready"
        )

        member = self._member()
        context['current_tier'] = member.tier_code if member else 'free'

        # 配額列該不該出現。三種人看不到：staff、tier 本來就無限的會員、
        # 以及對「這一款 edition」有永久解鎖的人（解鎖含該版本的無限查問）。
        #
        # 以前這裡是模板直接寫 {% if current_tier != 'subscriber' %}，那是全站
        # 最後一處 tier 字串比對，而且會把 admin tier 誤判成有配額。判準改成
        # 與 get_chat_limits() 同源，兩邊才不會一個說無限、一個畫進度條。
        user = self.request.user
        context['chat_unlimited_here'] = bool(
            user.is_authenticated and (
                user.is_staff or user.is_superuser
                or (member and (
                    member.has_unlocked(edition.id)
                    or member.limit('prompt_per_week') == -1
                ))
            )
        )

    def _flowchart_preview_chart(self, chart_filter):
        """
        ?preview=<flowchart_id> 指名、而且屬於這個版本的圖；不成立時回 None。

        只有具備 view 權限的後台人員會啟用。其他人帶這個參數一律當作沒帶：照常看
        公開版，不 404，也不透露那張草稿是否存在。
        """
        from django.core.exceptions import ValidationError
        from django.db.models import Q
        from game import flowchart_review as fr
        from game.models import RulebookFlowchart

        self._preview_chart = None
        preview_id = self.request.GET.get(fr.PREVIEW_PARAM)
        if not preview_id or not fr.can_preview(self.request.user):
            return None
        try:
            chart = (
                RulebookFlowchart.objects
                # 同版本但不是目前語言挑中的規則書，也允許預覽
                .filter(chart_filter | Q(rulebook__edition=self.object), pk=preview_id)
                .select_related("rulebook__language", "rulebook__edition")
                .distinct().first()
            )
        except (ValidationError, ValueError):
            chart = None
        self._preview_chart = chart
        return chart

    def _flowchart_context(self, context, content_rulebooks):
        """
        流程圖分頁 /games/<slug>/flowchart/。

        (rulebook, ruleset) 唯一：每個 ruleset 最多一張圖。多於一張時前端顯示
        ruleset 切換清單，以序號 key 對應各 viewer pane（ruleset 為自由文字，
        不適合直接當 DOM id）。

        一張圖除了透過自己的 rulebook 顯示外，也可能被直接標記為與其他 edition
        共用（linked_editions，例如同一遊戲的不同語言版本共用同一張流程圖，不需
        複製資料）——兩種來源以 OR 合併顯示。

        initial=False 的圖要有 tier feature 'flowchart_non_initial' 才看得到；
        沒有的會員／未登入者只能看 initial=True 的入門圖，其餘只在清單中顯示
        ruleset 名稱，內容不外流（不放進 viewer configs）。免費線與 ruleset 名稱
        無關，完全看 RulebookFlowchart.initial 這個旗標。

        開放對象有兩條互相獨立的路，是 OR 關係：
          1. tier.limits 的全域 feature flag（見 member/features.py）
          2. 這位會員對「這一款 edition」的永久解鎖（member.EditionUnlock，
             免費名額或 US$1 加購）——與 tier 脫鉤，訂閱過期降級也還在
        不要把其中一邊改寫成另一邊：全域旗標是「這個等級能不能」，解鎖是
        「這個人對這一款能不能」。
        """
        from django.db.models import Case, IntegerField, Q, When

        edition = self.object
        interface_lang = self._interface_lang()

        member = self._member()
        unlocked = bool(member and member.has_unlocked(edition.id))
        can_fc_non_initial = unlocked or bool(member and member.can('flowchart_non_initial'))
        context['can_flowchart_fullscreen'] = unlocked or bool(member and member.can('flowchart_fullscreen'))
        context['can_flowchart_print'] = unlocked or bool(member and member.can('flowchart_print'))
        context['can_flowchart_tour'] = unlocked or bool(member and member.can('flowchart_tour'))

        flowchart_charts = []
        flowchart_viewer_configs = []
        try:
            from game.models import RulebookFlowchart
            chart_filter = Q(linked_editions=edition)
            if content_rulebooks:
                chart_filter |= Q(rulebook__in=content_rulebooks)

            # 發布前預覽（?preview=<flowchart_id>，限後台人員）：那一張圖改顯示草稿，
            # 未發布的也加進來，其餘照常是公開版。沒權限的人帶這個參數一律忽略。
            preview_chart = self._flowchart_preview_chart(chart_filter)

            # 公開頁只讀 reviewer 核准的快照（publication.content），不讀編輯中的草稿
            charts = RulebookFlowchart.objects.published().filter(
                chart_filter,
            ).select_related("rulebook__language", "publication").distinct().annotate(
                initial_first=Case(
                    When(initial=True, then=0),
                    default=1,
                    output_field=IntegerField(),
                )
            ).order_by("display_order", "initial_first", "ruleset")
            if preview_chart is not None:
                preview_chart.initial_first = 0 if preview_chart.initial else 1
                charts = [c for c in charts if c.pk != preview_chart.pk] + [preview_chart]
            # 一個 ruleset 只留一張圖。同一版本的多本語言規則書可能各掛一張同名
            # ruleset 的圖，那是同一份內容的不同語言副本，重複列出只會變成兩顆
            # 一模一樣的 pill。留下的那張以「介面語言 → 英文 → 其他」為序挑，
            # 讓譯文缺漏時退回的原文最接近讀者的語言。
            lang_rank = {interface_lang: 0, "en": 1}
            charts = sorted(
                charts,
                key=lambda c: (
                    c.display_order, c.initial_first, c.ruleset,
                    lang_rank.get(
                        getattr(getattr(c.rulebook, "language", None), "language", None), 2
                    ),
                    str(c.id),
                ),
            )
            if preview_chart is not None:
                # 預覽的圖排第一：分頁預設顯示第一張，打開就是要看的那張；
                # 同名 ruleset 的公開版副本也因此讓位給草稿
                charts = [preview_chart] + [c for c in charts if c.pk != preview_chart.pk]
            seen_rulesets = set()
            for chart in charts:
                if chart.ruleset in seen_rulesets:
                    continue
                is_preview = preview_chart is not None and chart.pk == preview_chart.pk
                effective = chart.effective_json if is_preview else chart.publication.content
                if not effective:
                    # 空圖不佔用這個 ruleset 的名額，讓次順位語言的副本補上
                    continue
                seen_rulesets.add(chart.ruleset)
                # ruleset 選項名稱一律依介面語言顯示（查無譯文快取則退回原文）。
                from game.rag.flowchart.i18n import localize_text
                ruleset_label = localize_text(chart.ruleset, interface_lang)
                # 預覽的圖不鎖：讓沒有訂閱的後台帳號也看得到要檢查的內容
                locked = not is_preview and not chart.initial and not can_fc_non_initial
                key = f"rs{len(flowchart_charts)}"
                chart_entry = {
                    "key": key, "ruleset": chart.ruleset,
                    # 改善建議表單要指名對象（見 FlowchartSuggestionCreateView）
                    "id": str(chart.id),
                    "ruleset_label": ruleset_label, "locked": locked,
                    # 文字版大綱：付費鎖住的 ruleset 一律留 None，內容不進頁面原始碼。
                    "outline": None,
                }
                flowchart_charts.append(chart_entry)
                if locked:
                    continue
                # 一律自動在地化成目前介面語言（不再有付費翻譯按鈕/開關，所有會員含未登入者皆適用）。
                from game.rag.flowchart.i18n import localize
                effective = localize(effective, interface_lang)

                # 文字版（給不執行 JS 的爬蟲與輔助工具讀）。來源就是上面這份已在地化
                # 的顯示資料，所以文字與圖面完全一致，不是另生的隱藏內容。單獨
                # try：大綱組不出來也不能拖垮整個流程圖分頁（外層還有一個 blanket
                # except，會連 flowchart_charts 都吞掉）。
                try:
                    from game.rag.flowchart.outline import to_outline
                    chart_entry["outline"] = to_outline(effective)
                except Exception:
                    logger.exception("flowchart outline 產生失敗 chart=%s", chart.id)

                # 一張圖一份 config。以前桌機／手機各有一份 DOM，同一份
                # react_flow_json 因此要輸出兩次 —— 那是這一頁最大的 payload。
                flowchart_viewer_configs.append({
                    "mountId": f"fc-viewer-{key}",
                    "reactFlowData": effective,
                    "detail": chart.detail,
                    "rulebookTitle": edition.name,
                    "isAdjusted": True,
                    "readOnly": True,
                })
        except Exception:
            logger.exception("flowchart context 建構失敗 edition=%s", edition.id)

        # 網址指名了這一頁但這個版本根本沒有流程圖，代表網址本身就不成立，回 404
        # 而不是渲染一個空頁面。鎖住的付費內容不算「沒有內容」——分頁按鈕本來就會
        # 出現，只是顯示付費牆。
        if not flowchart_charts:
            raise Http404("This edition has no flowchart.")

        context["flowchart_charts"] = flowchart_charts
        context["flowchart_viewer_configs"] = flowchart_viewer_configs
        context["has_flowchart"] = True

        preview_chart = getattr(self, "_preview_chart", None)
        if preview_chart is not None:
            from game import flowchart_review as fr
            context["flowchart_preview"] = {
                "chart": preview_chart,
                "langs": fr.preview_urls(preview_chart, edition),
                "current_lang": interface_lang,
                "missing": fr.missing_translation_count(
                    preview_chart.effective_json, interface_lang,
                ),
            }

        # 階段數／步驟數只有這一頁算得出來，而且與頁面上文字版大綱看得到的數字
        # 一致 —— 拿來當 meta description 的具體內容，四個分頁的描述才真的不同。
        # 取第一張未鎖的圖（＝分頁預設顯示的那張）。
        outline = next(
            (fc["outline"] for fc in flowchart_charts if fc.get("outline")), None
        )
        phases = (outline or {}).get("phases") or []
        context["flowchart_outline"] = outline
        context["flowchart_phase_count"] = len(phases)
        context["flowchart_step_count"] = sum(len(p.get("steps") or []) for p in phases)

    def _script_context(self, context, content_rulebooks):
        """
        GM 講稿分頁 /games/<slug>/script/。

        單一已發布講稿，不做 ruleset 切換。來源：自己的 rulebook，或被直接連結
        （linked_editions）共用的講稿。
        """
        from django.db.models import Q

        edition = self.object
        interface_lang = self._interface_lang()

        member = self._member()
        can_view_script = bool(member and member.can('script'))

        script_data = None
        try:
            from game.models import RulebookScript
            script_filter = Q(linked_editions=edition)
            if content_rulebooks:
                script_filter |= Q(rulebook__in=content_rulebooks)
            scripts_qs = RulebookScript.objects.filter(script_filter, is_published=True)
            script_obj = (
                scripts_qs.filter(language__language=interface_lang).first()
                or scripts_qs.filter(language__language="en").first()
                or scripts_qs.first()
            )
            if script_obj and script_obj.effective_text:
                if can_view_script:
                    script_data = {
                        'title': script_obj.effective_title,
                        'text': script_obj.effective_text,
                        'host_persona': script_obj.host_persona,
                        'player_persona': script_obj.player_persona,
                        'atmosphere': script_obj.story_atmosphere,
                    }
                else:
                    # 未達訂閱等級：只露出正文開頭三段當預覽誘因（首段 blur、第二段
                    # 清楚、第三段淡出，見 panel_script.html），第四段起與三段人物
                    # 設定完全不進 context。
                    #
                    # 這三段都是未遮罩的真實文字：blur 與淡出純粹是視覺處理，那兩段
                    # 在原始碼裡跟中間清楚那段一樣讀得到 —— 本來就是要給人看的開頭。
                    # 打碼段落已經全部撤掉：原本人物設定與正文開頭是以同字集隨機亂碼
                    # 呈現，安全上沒問題，但爬蟲讀到的是沒有語意的字串，這一頁對 AI
                    # 回答引擎等於沒有內容。那個位置現在改放所有版本共用的通用說明，
                    # 由模板直接讀翻譯表（game.script.teaser.*）。
                    lines = [l for l in script_obj.effective_text.splitlines() if l]
                    script_data = {
                        # title 不在版面上渲染：只給 JSON-LD 的 Article headline
                        # 用。付費牆的標題本來就該讓爬蟲看得到，正文才是付費內容。
                        'title': script_obj.effective_title,
                        'locked': True,
                        # 切片而非索引：講稿不足三段時自然少渲染幾段，不會爆 IndexError
                        'text_preview_blur': lines[0:1],
                        'text_preview_clear': lines[1:2],
                        'text_preview_fade': lines[2:3],
                    }
        except Exception:
            logger.exception("script context 建構失敗 edition=%s", edition.id)

        if not script_data:
            raise Http404("This edition has no guide script.")

        context['script_data'] = script_data
        context['can_view_script'] = can_view_script
        context['has_script'] = True

    def _info_context(self, context, content_rulebooks):
        """遊戲資訊分頁 /games/<slug>/info/。"""
        edition = self.object

        user_interaction = None
        if self.request.user.is_authenticated:
            try:
                from interaction.models import Interaction
                user_interaction = Interaction.objects.filter(
                    member_id=self.request.user.id,
                    edition=edition
                ).first()
            except Exception:
                logger.exception("user_interaction 讀取失敗 edition=%s", edition.id)
        context['user_interaction'] = user_interaction

        game = edition.game
        context['has_skills'] = bool(
            game.adaptability or game.collaboration or game.communication or
            game.creativity or game.critical_thinking or game.problem_solving
        )

    def _add_unlock_context(self, context, edition):
        """Edition Access 的狀態旗標。

        info 分頁的完整區塊與各分頁右上角的 CTA 都讀這幾個旗標，由
        get_context_data() 對所有分頁一律呼叫。搜尋頁與收藏頁的絲帶只顯示狀態、
        不可點；動作入口只有這裡算出來的這幾個。
        模板會依這幾個旗標挑一種狀態顯示，所以它們要互斥得夠乾淨：
        can_pick / can_buy / can_release 任兩個都不會同時為真。

        「有沒有已發布流程圖」是兩條規則共用的前提：
          - 沒有圖 → 免費名額可以退回重選（還沒東西可解鎖）
          - 沒有圖 → 不讓買（付了錢可能永遠拿不到東西）
        兩者都走 selectors.editions_with_published_flowchart()，與搜尋卡片的
        流程圖徽章同源。
        """
        from django.conf import settings as dj_settings

        from game.selectors import editions_with_published_flowchart
        from member.models import EditionUnlock

        # 價格只是顯示用字串（實收金額由 Stripe price ID 決定），但兩個頁面要
        # 印同一組數字，所以統一從 settings 取，不要在模板裡各寫一份。
        context['edition_access_list_price'] = dj_settings.EDITION_ACCESS_LIST_PRICE
        context['edition_access_current_price'] = dj_settings.EDITION_ACCESS_CURRENT_PRICE

        member = self._member()
        context['unlock_is_authenticated'] = bool(member)
        if not member:
            # 未登入：其餘旗標一律假，模板顯示登入引導
            context['unlock_is_picked'] = False
            context['unlock_can_pick'] = False
            context['unlock_can_buy'] = False
            context['unlock_can_release'] = False
            return

        unlock = member.edition_unlocks.filter(edition=edition).first()
        used, quota = member.free_unlock_usage()
        has_flowchart = bool(editions_with_published_flowchart([edition.id]))

        context['unlock_free_used'] = used
        context['unlock_free_quota'] = quota
        context['unlock_has_flowchart'] = has_flowchart
        context['unlock_is_picked'] = unlock is not None
        context['unlock_source'] = unlock.source if unlock else None

        has_free_slot = (quota == -1 or used < quota)
        context['unlock_can_pick'] = unlock is None and has_free_slot
        context['unlock_can_buy'] = unlock is None and not has_free_slot and has_flowchart
        # 付費列一律不可退回：購買前就擋掉了沒有流程圖的 edition，
        # 這裡再擋一次是防禦性寫法（資料被手動改過也不會開後門）。
        context['unlock_can_release'] = bool(
            unlock is not None
            and unlock.source == EditionUnlock.Source.FREE
            and not has_flowchart
        )

    def _affiliate_context(self, context):
        """
        聯盟行銷廣告的 context。

        ⚠️ 目前沒有任何地方呼叫這個方法：唯一的消費端是 info／rulesbot 面板裡的
        廣告區塊，而那兩段在 partials/panel_rulesbot_desktop.html 與
        panel_rulesbot_mobile.html 裡整段是 {% comment %}。要讓廣告復活，兩邊要
        一起改（在 _rulesbot_context() 末尾呼叫這個方法，並解開那兩段註解），
        另外 get_queryset() 的 select_related 也要把 game__affiliate 加回去。
        """
        edition = self.object
        user_lang_code = self.request.GET.get('lang') or self._interface_lang()
        try:
            user_tribe = Tribe.objects.get(language=user_lang_code)
        except Tribe.DoesNotExist:
            user_tribe = None

        affiliate = edition.game.affiliate
        cta = None

        if not affiliate:
            # Fallback to a default affiliate if not set for the game
            from ad.models import Affiliate
            affiliate = Affiliate.objects.filter(
                name='Amazon Board Games',
                is_active=True
            ).first()
            if not affiliate:
                affiliate = Affiliate.objects.filter(
                    name__icontains='Amazon',
                    is_active=True
                ).first()

        if affiliate and affiliate.cta_name:
            from ad.models import CallToAction
            cta = CallToAction.objects.filter(
                name=affiliate.cta_name,
                tribe=user_tribe
            ).first() if user_tribe else None

            # Global fallback if no language-specific CTA found
            if not cta:
                cta = CallToAction.objects.filter(name=affiliate.cta_name).first()

        context['affiliate'] = affiliate
        context['cta'] = cta

        # Default Artwork if affiliate has none
        if affiliate and not affiliate.artwork:
            from ad.models import Artwork
            context['default_affiliate_artwork'] = Artwork.objects.filter(title='Amazon Board Games').first()
        else:
            context['default_affiliate_artwork'] = None

    # ── 結構化資料 ───────────────────────────────────────────────────

    # 分頁 → (WebPage 的 schema 型別, 分頁名稱的翻譯 key)。分頁名稱用分頁列上那顆
    # 按鈕的字，麵包屑第三層才會跟讀者看到的一致。
    TAB_JSONLD = {
        "chat": ("WebPage", None),
        "flowchart": ("WebPage", "game.flowchart.title"),
        "script": ("WebPage", "game.script.title"),
        "info": ("ItemPage", "game.info.title"),
    }

    def _add_jsonld(self, context, tab):
        """
        覆寫 context processor 那個通用的 WebPage 節點，補上 about 指向本頁的 Game，
        再依分頁加一個「只有這一頁有」的節點。

        author 仍是 Tabuney —— 這頁的 flowchart、講稿、Rulesbot 都是站方產出，
        遊戲設計師掛在 Game 節點的 creator，兩者不能混。

        Game 節點四頁都保留，不是只放在 info 頁：搜尋／AI 引擎只在同一頁的 @graph
        內解析 @id，只在一頁定義、其他頁留懸空引用等於把那幾頁的主體資訊抽空。
        而 Game 的 @id 固定用預設語言網址（見 structured_data），四頁完全相同——
        四個網址因此都宣告「我在講同一個實體」，互相加強而不是被判重複。
        WebPage 的 @id 來自 request.path，本來就 per-tab 唯一。
        """
        from game.structured_data import (
            edition_jsonld, flowchart_howto_jsonld, script_article_jsonld, webpage_jsonld,
        )

        edition = self.object
        page_type, tab_name_key = self.TAB_JSONLD[tab]

        # Rulesbot 分頁按鈕的字是寫死的 "Rulesbot"（沒有翻譯 key），麵包屑照辦
        tab_name = "Rulesbot" if tab == "chat" else None
        if tab_name_key:
            from translation.selectors import get_translation
            tab_name = get_translation(self._interface_lang(), tab_name_key)

        url_tab = tab if tab != self.DEFAULT_TAB else None
        game_nodes = edition_jsonld(
            edition, self.request, settings.SITE_URL,
            tab=url_tab, tab_name=tab_name,
        )
        game_id = game_nodes[0]['@id']

        nodes = [
            # 網址必須與 context processor 的 canonical 完全一致（含語言前綴），
            # 否則 @id 對不上，去重失效會留下兩個 WebPage 節點。
            webpage_jsonld(
                settings.SITE_URL,
                settings.SITE_URL + self.request.path,
                page_type=page_type,
                about_id=game_id,
            ),
            *game_nodes,
        ]

        page_url = settings.SITE_URL + self.request.path
        if tab == "flowchart":
            # rulesbot 分頁刻意沒有對應節點：那頁沒有任何伺服器端渲染的問答內容，
            # 掛一個 mainEntity 為空的 QAPage/FAQPage 是 spam 訊號（同 faq_jsonld）。
            howto = flowchart_howto_jsonld(
                page_url,
                f"How to play {edition.name or edition.game.canonical_name}",
                context.get("flowchart_outline"),
                about_id=game_id,
            )
            if howto:
                nodes.append(howto)
        elif tab == "script":
            script_data = context.get("script_data") or {}
            nodes.append(script_article_jsonld(
                settings.SITE_URL, page_url,
                headline=script_data.get("title"),
                locked=bool(script_data.get("locked")),
                about_id=game_id,
            ))

        context['jsonld_nodes'] = nodes
