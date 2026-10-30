"""
Game / Edition 的查詢邏輯，與 HTTP 無關。

網站的 HTML view（game/views/original_views.py）與 App 的 JSON API（game/api_views.py）
都呼叫這裡，兩邊共用同一份查詢與標註規則。任何需要 request 的東西（log_search、
log_view、語言判斷）都留在各自的 view 層。
"""

import logging
import random
from typing import NamedTuple
from urllib.parse import urlparse

from django.db.models import (
    Case, Exists, ExpressionWrapper, F, FloatField, IntegerField,
    OuterRef, Q, Value, When,
)
from django.db.models.functions import Greatest, Length, Power
from django.utils import timezone

from game.models import Edition, Game
from game.rag.constants import WHOLE_BUNDLE_MAX_DOCS, WHOLE_BUNDLE_MAX_TOKENS

logger = logging.getLogger(__name__)


class EditionSearchResult(NamedTuple):
    """
    search_editions() 的回傳值。

    matched_by 是給 stats.log_search 用的：光看結果數分不出「條碼掃不到」和
    「打錯字」，但前者可以直接反查是哪一款遊戲該補。
    """
    editions: object      # QuerySet[Edition]，已排序
    matched_by: str       # 'barcode' | 'edition_name' | 'game_title' | 'none'


def search_editions(query):
    """
    依 query 找 Edition。比對順序：條碼 → Edition 名稱 → Game 標題。
    找到就停，不合併結果。

    回傳 EditionSearchResult(editions, matched_by)。matched_by 不能改成掛在
    queryset 上的屬性 —— .order_by() 會 clone queryset，屬性會被丟掉。
    """
    matched_by = 'barcode'
    results = Edition.objects.filter(barcode=query, game__kind="standalone")
    if not results.exists():
        matched_by = 'edition_name'
        results = Edition.objects.filter(name__unaccent__icontains=query, game__kind="standalone")
    if not results.exists():
        matched_by = 'none'
        games = Game.objects.filter(titles__title__unaccent__icontains=query, kind="standalone")
        if games.exists():
            matched_by = 'game_title'
            results = Edition.objects.filter(game__in=games)
    if results.exists():
        results = results.select_related(
            'game', 'language'
        ).prefetch_related('rulebooks', 'roles__entity')
    else:
        matched_by = 'none'
    # 排序跟 /games/ 瀏覽頁同一套分值規則（annotate_rank_score），搜尋結果也是資料
    # 越完整、越新的排越前面。id 這個 tiebreak 不能省：Paginator 在未排序的 queryset
    # 上分頁，「載入更多」會重複或漏掉資料。
    results = annotate_rank_score(results).order_by(
        '-rank_score', F('release_year').desc(nulls_last=True), 'id',
    )
    return EditionSearchResult(results, matched_by)


# ---- 搜尋框的即時建議 ------------------------------------------------------

AUTOCOMPLETE_MIN_CHARS = 2
AUTOCOMPLETE_LIMIT = 8


def _autocomplete_page(editions, query, limit):
    """
    建議清單的排序：前綴命中 → 名稱短的 → 字母序。

    刻意不用 annotate_rank_score()：那是為整頁結果設計的，會多帶好幾個
    Exists 子查詢，對每次鍵入都要跑一遍的端點太重。建議清單只有 8 筆，
    使用者是用眼睛掃的，「開頭就對上」比「資料完整度」有用得多。

    id 這個 tiebreak 跟 search_editions 一樣不能省，否則同分的順序會在
    連續兩次鍵入之間跳動。
    """
    return list(
        editions.annotate(
            _prefix_hit=Case(
                When(name__unaccent__istartswith=query, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        .only('id', 'name', 'slug', 'thumbnail')
        .order_by('_prefix_hit', Length('name'), 'name', 'id')[:limit]
    )


def autocomplete_editions(query, limit=AUTOCOMPLETE_LIMIT):
    """
    搜尋框輸入時的即時建議，回傳最多 limit 筆 Edition（list，非 queryset）。

    比對順序刻意與 search_editions() 相同（條碼 → Edition 名稱 → Game 標題），
    建議清單才會是「按下 Enter 會看到的結果」的前幾筆；兩邊若各用一套規則，
    使用者會遇到下拉有、送出後卻不見的鬼打牆。

    與 search_editions 的差別只有三點：不算 rank_score、限筆數、不記 log。
    每一段直接取回 list 而不是先 .exists() 再查一次 —— 這裡是每次鍵入都會打的
    端點，能少一趟 round trip 就少一趟。

    少於 AUTOCOMPLETE_MIN_CHARS 個字直接回空清單：一個字元能對上的東西太多，
    給出來的 8 筆等於亂數，是雜訊不是建議。門檻設 2 而不是 3，是因為資料裡
    有 'Ys'、'地主' 這種兩字名字，設 3 它們就永遠叫不出來，而 CJK 兩個字
    本來就常常是完整詞。
    """
    query = (query or '').strip()
    if len(query) < AUTOCOMPLETE_MIN_CHARS:
        return []

    standalone = Edition.objects.filter(game__kind='standalone')

    rows = _autocomplete_page(standalone.filter(barcode=query), query, limit)
    if rows:
        return rows

    rows = _autocomplete_page(
        standalone.filter(name__unaccent__icontains=query), query, limit
    )
    if rows:
        return rows

    games = Game.objects.filter(
        titles__title__unaccent__icontains=query, kind='standalone'
    )
    return _autocomplete_page(Edition.objects.filter(game__in=games), query, limit)


def rulesbot_ready_rulebooks():
    """
    rulesbot 能回答的 Rulebook：whole_context 非空即可。

    2026-08 起 RAG 停用，問答一律走 whole-context，所以就緒判準從
    status="indexed"（需要 chunk 進 RulebookNode + Qdrant）換成這個。
    所有「這本規則書能不能聊天」的判斷都該用這個函式，不要各自寫條件。

    ⚠️ 要判斷 Edition 是否就緒，請用 filter(rulebooks__in=rulesbot_ready_rulebooks())，
    不要寫 Edition.objects.exclude(rulebooks__whole_context="")——後者在反向多值
    關聯上語意完全不同，會把「完全沒有 rulebook」的 edition 也算成就緒。
    """
    from game.models import Rulebook
    return Rulebook.objects.exclude(whole_context="")


def featured_editions(limit):
    """首頁 / 空查詢時的隨機精選：rulesbot 已就緒且有封面圖的版本。"""
    return Edition.objects.filter(
        rulebooks__in=rulesbot_ready_rulebooks(),
        thumbnail__isnull=False,
    ).exclude(thumbnail="").select_related('game').distinct().order_by('?')[:limit]


def random_flowchart_editions(limit):
    """首頁「熱門攻略」用：隨機挑已發布流程圖、且有封面圖的版本，同一款遊戲只出現一次。

    流程圖來源與 editions_with_published_flowchart() 一致：自己 rulebook 底下的圖，
    加上直接共用（linked_editions）的。多撈幾筆再按 game 去重，避免同一款遊戲的
    不同版本佔掉多格。
    """
    from game.models import RulebookFlowchart

    published = RulebookFlowchart.objects.published()
    edition_ids = set(published.values_list('rulebook__edition_id', flat=True))
    edition_ids |= set(published.values_list('linked_editions__id', flat=True))
    edition_ids.discard(None)

    candidates = (
        Edition.objects.filter(id__in=edition_ids, thumbnail__isnull=False)
        .exclude(thumbnail="").select_related('game').order_by('?')[:limit * 4]
    )
    picked, seen_games = [], set()
    for ed in candidates:
        if ed.game_id in seen_games:
            continue
        seen_games.add(ed.game_id)
        picked.append(ed)
        if len(picked) == limit:
            break
    return picked


# 首頁 hero 的 Step Flow 示範用哪一張圖。改成別款遊戲只要換這兩個常數。
HERO_FLOW_EDITION_SLUG = "6-nimmt-version-10"
HERO_FLOW_RULESET = "Default"
# 示範一開始停在哪個節點：用原文（未翻譯）的標題找，因為節點 id 是編輯器隨機產的。
HERO_FLOW_INITIAL_LABEL = "Higher than rightmost card in any row?"


def _flow_phase_slot(data):
    """動作節點的階段色槽 1/2/3（準備／遊戲流程／終局），無則 0。

    與前端 admin_frontend/src/nodes/index.tsx 的 phaseSlot() 同一套判準：
    phase_order 最可靠，phase_id／phase_label 的關鍵字只是沒有 order 時的備援。
    """
    import re

    order = data.get("phase_order")
    if order in (1, 2, 3):
        return order
    hay = f'{data.get("phase_id") or ""} {data.get("phase_label") or ""}'.lower()
    if not hay.strip():
        return 0
    if re.search(r"setup|prepar", hay):
        return 1
    if re.search(r"end|final|scor", hay):
        return 3
    if re.search(r"sequence|flow|play|round|turn", hay):
        return 2
    return 0


def _flow_node_box(node):
    """節點在畫布上的位置與實際尺寸（x, y, w, h）。實際量到的尺寸優先，其次是 width/height，最後是 style。"""
    size = node.get("measured") or {}
    style = node.get("style") or {}
    pos = node.get("position") or {}
    return {
        "x": pos.get("x", 0),
        "y": pos.get("y", 0),
        "w": size.get("width") or node.get("width") or style.get("width") or 140,
        "h": size.get("height") or node.get("height") or style.get("height") or 50,
    }


def _flow_edges_and_view(shown, nodes):
    """Full Flowchart 示意圖要畫的邊（路徑 d、顏色、標籤位置）與 viewBox。

    viewBox 取節點與邊路徑座標的外框再留邊，這樣不論哪一張圖都不會被裁到。
    """
    import re

    edges = []
    xs, ys = [], []
    for nd in nodes.values():
        xs += [nd["x"], nd["x"] + nd["w"]]
        ys += [nd["y"], nd["y"] + nd["h"]]
    for e in shown.get("edges", []):
        data = e.get("data") or {}
        if e["source"] not in nodes or e["target"] not in nodes or not data.get("d"):
            continue
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", data["d"])]
        xs += nums[0::2]
        ys += nums[1::2]
        edges.append({
            "d": data["d"],
            "stroke": (e.get("style") or {}).get("stroke") or "var(--fc-edge-stroke)",
            "label": e.get("label") or "",
            "lx": data.get("labelX"),
            "ly": data.get("labelY"),
        })
    pad = 24
    view = [min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad]
    return edges, view


def hero_step_flow(lang):
    """首頁 hero 的 Step Flow 示範資料：真實已發布流程圖，依 lang 在地化。

    只留步驟瀏覽需要的最小結構（節點標題／種類、每個節點的出邊與分支標籤），
    不把版面座標與樣式送到前端。找不到圖時回 None，模板就不輸出示範。
    """
    from django.db.models import Q
    from game.models import RulebookFlowchart
    from game.rag.flowchart.i18n import localize

    edition = Edition.objects.filter(slug=HERO_FLOW_EDITION_SLUG).first()
    if edition is None:
        return None

    chart = (
        RulebookFlowchart.objects.published()
        .filter(Q(linked_editions=edition) | Q(rulebook__edition=edition),
                ruleset=HERO_FLOW_RULESET)
        .select_related("publication").distinct().first()
    )
    raw = chart.publication.content if chart else None
    if not raw or not raw.get("nodes"):
        return None

    shown = localize(raw, lang)
    kinds = {"start", "end", "action", "decision", "parallel"}
    nodes = {
        n["id"]: {
            "label": n["data"].get("label", ""),
            "kind": n["data"]["kind"],
            "phase": _flow_phase_slot(n["data"]),
            **_flow_node_box(n),
        }
        for n in shown["nodes"]
        if (n.get("data") or {}).get("kind") in kinds
    }
    out = {nid: [] for nid in nodes}
    for e in shown.get("edges", []):
        if e["source"] in nodes and e["target"] in nodes:
            out[e["source"]].append({"to": e["target"], "label": e.get("label") or ""})

    def first_id(kind=None, label=None):
        for n in raw["nodes"]:
            d = n.get("data") or {}
            if n["id"] in nodes and (kind is None or d.get("kind") == kind)                     and (label is None or d.get("label") == label):
                return n["id"]
        return None

    edges, view = _flow_edges_and_view(shown, nodes)
    return {
        "nodes": nodes,
        "out": out,
        "edges": edges,
        "view": view,
        "first": first_id("start"),
        "last": first_id("end"),
        "initial": first_id(label=HERO_FLOW_INITIAL_LABEL) or first_id("start"),
    }


# ---- 瀏覽頁排序分值 --------------------------------------------------------
#
# 分值 = 資料完整性(0-5) + 新發布程度(0-3)，滿分 8。
#
# 刻意即時計算、不在 Edition 存欄位：公式會不定期調整（存了就要每次 backfill），
# 「今年」每年 1/1 會變（存了就要掛 cron），而完整性的輸入分散在四個 model
# （RulebookScript / RulebookFlowchart / Rulebook / Dimension），要維持存量欄位
# 就得在四處掛 signal —— 而這個專案刻意沒有任何 signal。對照 Game.cq 之所以能存
# 欄位，是因為它只依賴 Game 自己的六個欄位，save() 就維護得了。
#
# 呼叫端只碰 annotate_rank_score() / browse_editions_page()，所以哪天 Edition 大到
# 排序真的變慢，改成讀存量欄位 + 一支 recalc 指令就好，呼叫端不用動。

COMPLETENESS_SCRIPT = 5
COMPLETENESS_FLOWCHART = 4
COMPLETENESS_RAG = 3
COMPLETENESS_DIM_ART = 2
COMPLETENESS_DIM_BGG = 1

RECENCY_WEIGHT = 3.0    # w
RECENCY_DECAY = 0.7     # c

# 前 10 名互相打散、11-30 名互相打散，之後照分數排
SHUFFLE_BANDS = ((0, 10), (10, 30))
BROWSE_HEAD = SHUFFLE_BANDS[-1][1]

_SOURCE_ID_CACHE = {}


def _dimension_source_id(username):
    """
    Dimension.source_member 用的 art / bgg 帳號 pk。

    本地與 VPS 是兩個獨立資料庫（見 models.py 對 UUID pk 的說明），Member pk 不保證
    一致，所以一律用帳號名查。查不到就回 None 且不快取，等帳號建好下次再查。
    """
    if username not in _SOURCE_ID_CACHE:
        from member.models import Member

        pk = Member.objects.filter(id__username=username).values_list('pk', flat=True).first()
        if pk is None:
            return None
        _SOURCE_ID_CACHE[username] = pk
    return _SOURCE_ID_CACHE[username]


def annotate_rank_score(queryset, today=None):
    """
    在 Edition queryset 上掛 completeness_score / recency_score / rank_score。

    /games/ 瀏覽頁與 admin 的 Edition list 共用這一份定義，兩邊的分值一定一致。
    完整性的 script / flowchart 判定條件與 annotate_editions() 完全對齊（含
    linked_editions），否則卡片上的徽章會跟排序分值對不起來。
    """
    from game.models import Dimension, Rulebook, RulebookFlowchart, RulebookScript

    this_year = (today or timezone.localdate()).year

    # 「自己的 rulebook 底下」與「被 linked_editions 共用」要拆成兩個 EXISTS 再 OR，
    # 不能寫成單一子查詢裡的 Q(...) | Q(...)：那會讓 exclude 與 m2m join 疊在一起，
    # Postgres 挑出來的計畫是分開寫的 45 倍慢（實測 2200ms vs 49ms）。
    script = RulebookScript.objects.filter(is_published=True)
    has_script_own = script.filter(rulebook__edition=OuterRef('pk'))
    has_script_linked = script.filter(linked_editions=OuterRef('pk'))

    # 已發布＝有 reviewer 核准的快照，核准時已擋掉空圖，不必再判斷內容是否為空
    flowchart = RulebookFlowchart.objects.published()
    has_flowchart_own = flowchart.filter(rulebook__edition=OuterRef('pk'))
    has_flowchart_linked = flowchart.filter(linked_editions=OuterRef('pk'))
    # rulesbot ready 只算這個版本自己底下就緒的規則書（等同卡片的 chat 徽章 matched 狀態）
    is_rag_ready = rulesbot_ready_rulebooks().filter(edition=OuterRef('pk'))
    # Dimension 有 uq_dimension_game，一款遊戲只有一筆，所以 art / bgg 天然互斥
    dim_art = Dimension.objects.filter(
        game=OuterRef('game_id'), source_member_id=_dimension_source_id('art'),
    )
    dim_bgg = Dimension.objects.filter(
        game=OuterRef('game_id'), source_member_id=_dimension_source_id('bgg'),
    )

    completeness = Case(
        When(Q(Exists(has_script_own)) | Q(Exists(has_script_linked)),
             then=Value(COMPLETENESS_SCRIPT)),
        When(Q(Exists(has_flowchart_own)) | Q(Exists(has_flowchart_linked)),
             then=Value(COMPLETENESS_FLOWCHART)),
        When(Exists(is_rag_ready), then=Value(COMPLETENESS_RAG)),
        When(Exists(dim_art), then=Value(COMPLETENESS_DIM_ART)),
        When(Exists(dim_bgg), then=Value(COMPLETENESS_DIM_BGG)),
        default=Value(0),
        output_field=FloatField(),
    )

    # w * 1 / (t - p + 1)^c。Greatest 是防呆：預購版的 p 可能大於今年，
    # 底數變成 0 就會除零。
    age = Greatest(
        ExpressionWrapper(
            Value(this_year + 1) - F('release_year'), output_field=IntegerField(),
        ),
        Value(1),
    )
    recency = Case(
        When(release_year__isnull=True, then=Value(0.0)),   # 沒填出版年就是 0 分
        default=ExpressionWrapper(
            Value(RECENCY_WEIGHT) / Power(age, Value(RECENCY_DECAY)),
            output_field=FloatField(),
        ),
        output_field=FloatField(),
    )

    return queryset.annotate(
        completeness_score=completeness,
        recency_score=recency,
    ).annotate(
        rank_score=F('completeness_score') + F('recency_score'),
    )


def browse_editions_queryset():
    """/games/ 無查詢時的完整瀏覽清單，依分值高低排序。"""
    return annotate_rank_score(
        Edition.objects.select_related('game', 'language')
    ).order_by(
        # id 這個 tiebreak 不能省，否則「載入更多」會重複或漏資料。
        # release_year 要 nulls_last：Postgres 的 DESC 預設把 NULL 排最前面。
        '-rank_score', F('release_year').desc(nulls_last=True), 'id',
    )


def browse_editions_page(offset, limit, seed):
    """
    取瀏覽清單的一頁，回傳 (editions, has_next)。

    前 BROWSE_HEAD 名要按 SHUFFLE_BANDS 打散。seed 由第一次整頁載入時產生、之後
    每次「載入更多」帶回來 —— 少了它就只能用 order_by('?')，而那個沒辦法分頁
    （下一頁會重新洗牌，結果既重複又漏）。seed 走 query param 不進 session，
    維持匿名訪客零 cookie。
    """
    qs = browse_editions_queryset()
    total = Edition.objects.count()

    if offset >= BROWSE_HEAD:
        items = list(qs[offset:offset + limit])
    else:
        head = list(qs[:BROWSE_HEAD])
        rng = random.Random(seed)          # 同一個 seed 必定洗出同一個順序
        for start, end in SHUFFLE_BANDS:
            band = head[start:end]
            rng.shuffle(band)
            head[start:end] = band
        items = head[offset:offset + limit]
        if len(items) < limit:             # 跨過 head 邊界的那一頁，往後補滿
            items += list(qs[BROWSE_HEAD:BROWSE_HEAD + limit - len(items)])

    return items, (offset + len(items)) < total


def editions_with_published_flowchart(edition_ids):
    """這批 edition 裡，哪些有至少一張「看得到內容」的已發布流程圖。

    回傳 edition id 的 set。判準兩件事，缺一不可：
      1. 已發布（RulebookFlowchart.objects.published()，即有 reviewer 核准且未下架的
         FlowchartPublication）。核准時已擋掉空圖，所以已發布必然有內容，對應
         _flowchart_context 裡的 `if not effective: continue`。
      2. 來源兩種都算：自己 rulebook 底下的圖，以及被直接標記共用的
         （linked_editions，例如同款遊戲不同語言版本共用同一張圖）。

    這是「這款 edition 有沒有流程圖」的唯一批次判準，三個地方共用：
    搜尋卡片的流程圖徽章、免費解鎖名額可否退回、US$1 加購可否購買。
    後兩者是使用者定的規則（「還沒有流程圖就等於還沒東西可解鎖」），
    判準一旦與徽章分家，就會出現「卡片說有圖、卻說可以退回」這種矛盾。

    ⚠️ 單一 edition 的版本是 edition_tab_flags()，它走的是已解析好的
    content_rulebooks（含語言挑選），不是這裡的 rulebook__edition_id，
    兩者的空圖判準必須保持一致。
    """
    from game.models import RulebookFlowchart

    edition_ids = list(edition_ids)
    if not edition_ids:
        return set()

    non_empty = RulebookFlowchart.objects.published()

    found = set(
        non_empty.filter(rulebook__edition_id__in=edition_ids)
        .values_list('rulebook__edition_id', flat=True).distinct()
    )
    found |= set(
        non_empty.filter(linked_editions__id__in=edition_ids)
        .values_list('linked_editions__id', flat=True).distinct()
    )
    return found


def annotate_editions(editions_list):
    """
    在一批 Edition 實例上掛出卡片要顯示的衍生欄位（不寫回資料庫）：
      search_chat_status / search_has_flowchart / search_has_script / search_has_skills

    刻意用批次查詢而非逐筆屬性，避免搜尋結果頁的 N+1。
    """
    if not editions_list:
        return editions_list

    from game.models import Rulebook

    edition_ids = [ed.id for ed in editions_list]
    game_ids = list({ed.game_id for ed in editions_list})

    indexed_edition_ids = set(
        rulesbot_ready_rulebooks().filter(edition_id__in=edition_ids)
        .values_list('edition_id', flat=True)
    )
    linked_game_ids = set(
        rulesbot_ready_rulebooks().filter(edition__game_id__in=game_ids)
        .values_list('edition__game_id', flat=True)
    )

    has_flowchart_edition_ids = set()
    try:
        has_flowchart_edition_ids = editions_with_published_flowchart(edition_ids)
    except Exception:
        pass

    has_script_edition_ids = set()
    try:
        from game.models import RulebookScript
        has_script_edition_ids = set(
            RulebookScript.objects.filter(
                rulebook__edition_id__in=edition_ids, is_published=True,
            ).values_list('rulebook__edition_id', flat=True).distinct()
        )
        # 直接共用連結(linked_editions)的 edition 也算擁有講稿，不限於自己 rulebook 底下的。
        has_script_edition_ids |= set(
            RulebookScript.objects.filter(
                linked_editions__id__in=edition_ids, is_published=True,
            ).values_list('linked_editions__id', flat=True).distinct()
        )
    except Exception:
        pass

    for ed in editions_list:
        if ed.id in indexed_edition_ids:
            ed.search_chat_status = "matched"
        elif ed.game_id in linked_game_ids:
            ed.search_chat_status = "linked"
        else:
            ed.search_chat_status = "not_ready"
        ed.search_has_flowchart = ed.id in has_flowchart_edition_ids
        ed.search_has_script = ed.id in has_script_edition_ids
        g = ed.game
        ed.search_has_skills = bool(
            g.adaptability or g.collaboration or g.communication or
            g.creativity or g.critical_thinking or g.problem_solving
        )
    return editions_list


def annotate_member_interactions(editions_list, member):
    """
    在一批 Edition 實例上掛出「這位會員自己的狀態」：
      member_status / member_rating（收藏／喜好，沒有紀錄就是 None）
      search_is_unlocked（是否為這位會員永久解鎖的 edition）

    跟 annotate_editions() 分開，是因為那個是所有人共用、可快取的資料，
    這個是每位會員各自不同；API 也還沒有這個需求。member 為 None
    （匿名訪客）時一律掛 None/False，模板就不會輸出任何標記。
    """
    if not editions_list:
        return editions_list

    status_map = {}
    unlocked_ids = set()
    if member is not None:
        from interaction.models import Interaction
        status_map = {
            edition_id: (status, rating)
            for edition_id, status, rating in Interaction.objects.filter(
                member=member, edition_id__in=[ed.id for ed in editions_list],
            ).values_list('edition_id', 'status', 'rating')
        }
        # 一位會員的解鎖數是個位數，整批撈比逐頁 IN 查詢更省，也讓同一個
        # request 內後續的查詢直接吃 Member 實例上的快取。
        unlocked_ids = member.unlocked_edition_ids()

    for ed in editions_list:
        ed.member_status, ed.member_rating = status_map.get(ed.id, (None, None))
        ed.search_is_unlocked = ed.id in unlocked_ids
    return editions_list


class ChatBundle(NamedTuple):
    """
    resolve_chat_bundle() 的回傳值：這次問答要餵給模型的那一組規則書。

    rulebooks 是同一個 edition、同一種語言下的全部就緒規則書（主規則書 + 擴充
    說明 + FAQ 之類），一起進 prompt。空 list 代表 status == 'not_ready'。
    """
    rulebooks: list        # list[Rulebook]，順序即 prompt 內的 Ref 1/2/3...
    source_edition: object # 規則書實際所屬的 Edition（linked 時與傳入的不同）
    status: str            # 'matched' | 'linked' | 'not_ready'


def _bundle_token_estimate(rulebook):
    """
    打包上限用的 token 估算。pdf_token_count 是 parse 時寫入的，舊資料可能是
    None（見 Rulebook.pdf_token_count），退回用字元數 / 4 粗估——這個值只用來
    卡上限，不需要精確。

    字元數優先讀 whole_context_len 這個 annotation（見 _ready_for_bundle）。
    沒有 annotation 時才碰 whole_context 本身，那會把整份規則書全文載進記憶體。
    """
    if rulebook.pdf_token_count:
        return rulebook.pdf_token_count
    length = getattr(rulebook, "whole_context_len", None)
    if length is None:
        length = len(rulebook.whole_context or "")
    return length // 4


def _ready_for_bundle():
    """
    打包解析用的 Rulebook queryset：就緒判準與 rulesbot_ready_rulebooks() 相同，
    但把三個巨大的 TextField 擋在外面。

    resolve_chat_bundle() 每次 edition 詳細頁渲染都會跑，而一個 edition 底下最多
    掛過 35 本規則書；不 defer 的話光是挑書就要把 35 份規則書全文載進記憶體，而
    這條路徑只需要 title / language / token 數。真正要用全文的是
    RagService.answer_question_whole()，它拿 id 自己重查。
    """
    return (
        rulesbot_ready_rulebooks()
        .select_related("language")
        .defer("whole_context", "extracted_text", "processed_text")
        .annotate(whole_context_len=Length("whole_context"))
    )


def _language_group(rulebooks, tribe):
    """rulebooks 裡屬於 tribe 的那些，保持傳入順序。"""
    if not tribe:
        return []
    return [rb for rb in rulebooks if rb.language_id == tribe.id]


def resolve_chat_bundle(edition, lang_code=None):
    """
    決定這次問答要用哪一組規則書，回傳 ChatBundle。

    規則書打包的單位是「一個 edition + 一種語言」——同一個 edition 底下同語言的
    規則書會全部一起進 prompt，讓使用者不必切換文件就能問到擴充/FAQ 的內容。

    為什麼要先依語言分組，而不是直接把 edition 底下全部拿來打包：scraper 是一個
    語言 URL 抓一本，所以多本的 edition 絕大多數是同一份文件的 N 種語言版本
    （Dixit Odyssey 有 35 本）。全部打包等於把同樣內容重複塞 35 次。依語言分組
    之後，剩在同一組的才是真正不同的文件。

    語言的 fallback 順序：介面語言 → 英文 → 就緒本數最多的語言。
    edition 的 fallback 沿用既有行為：自己沒有就借同一款遊戲其他版本的（linked，
    開場白會標示出處）。

    ⚠️ rulebooks 的順序必須是決定性的。它決定 build_whole_context_prompt() 可
    快取前綴的位元組內容，順序一浮動，那個 edition 的 prompt cache 就整個 miss。
    """
    from game.models import Tribe

    ready = _ready_for_bundle()

    def _ordered(qs):
        # created_at + id：created_at 同秒（批次匯入很常見）時才不會退化成任意順序
        return list(qs.order_by("created_at", "id"))

    own = _ordered(ready.filter(edition=edition))
    if own:
        candidates, source_edition, status = own, edition, "matched"
    else:
        alt = _ordered(
            ready.filter(edition__game=edition.game).select_related("edition")
        )
        if not alt:
            return ChatBundle([], None, "not_ready")
        # 借用時只認其中一個 edition，不跨版本混搭——不同版本的規則本來就可能牴觸
        source_edition = alt[0].edition
        candidates = [rb for rb in alt if rb.edition_id == source_edition.id]
        status = "linked"

    # ---- 語言分組，逐級 fallback ----
    tribe = None
    if lang_code:
        try:
            tribe = Tribe.objects.get(language=lang_code)
        except Tribe.DoesNotExist:
            tribe = None

    group = _language_group(candidates, tribe)

    if not group and lang_code != "en":
        try:
            group = _language_group(candidates, Tribe.objects.get(language="en"))
        except Tribe.DoesNotExist:
            group = []

    if not group:
        # 最後手段：挑就緒本數最多的語言。用 language_id 當平手時的第二鍵，
        # 才不會每次請求挑到不同語言（= prompt cache 每次都 miss）。
        by_lang = {}
        for rb in candidates:
            by_lang.setdefault(rb.language_id, []).append(rb)
        if by_lang:
            best = max(by_lang.items(), key=lambda kv: (len(kv[1]), str(kv[0])))
            group = best[1]

    if not group:
        return ChatBundle([], None, "not_ready")

    # ---- 上限保護 ----
    bundle, total = [], 0
    for rb in group:
        if len(bundle) >= WHOLE_BUNDLE_MAX_DOCS:
            logger.warning(
                "chat bundle for edition %s hit WHOLE_BUNDLE_MAX_DOCS (%s); "
                "dropping %s rulebook(s)",
                source_edition.id, WHOLE_BUNDLE_MAX_DOCS, len(group) - len(bundle),
            )
            break
        est = _bundle_token_estimate(rb)
        if bundle and total + est > WHOLE_BUNDLE_MAX_TOKENS:
            logger.warning(
                "chat bundle for edition %s hit WHOLE_BUNDLE_MAX_TOKENS (%s at %s tokens); "
                "dropping %s rulebook(s)",
                source_edition.id, WHOLE_BUNDLE_MAX_TOKENS, total, len(group) - len(bundle),
            )
            break
        bundle.append(rb)
        total += est

    return ChatBundle(bundle, source_edition, status)


def resolve_chat_status(edition):
    """
    這個版本的聊天可用狀態：
      matched   — 這個版本自己就有就緒的規則書
      linked    — 同一款遊戲的其他版本有就緒的規則書
      not_ready — 都沒有

    刻意維持成兩個 exists()，不轉呼叫 resolve_chat_bundle()：這個函式被
    EditionSerializer 逐筆呼叫（見 edition_serializers.py:100），跑完整的打包
    解析等於在列表端點上多做語言分組與 Tribe 查詢。

    兩者的就緒判準都來自 rulesbot_ready_rulebooks()，而 resolve_chat_bundle()
    的語言 fallback 最後一級一定會挑出至少一本，所以只要 edition 層的分支條件
    與這裡一致，兩邊給的 status 就一致。改其中一邊記得看另一邊。
    """
    ready = rulesbot_ready_rulebooks()
    if ready.filter(edition=edition).exists():
        return 'matched'
    if ready.filter(edition__game=edition.game).exists():
        return 'linked'
    return 'not_ready'


def rulebook_source_link(rulebooks):
    """
    工具列「書本」按鈕的狀態：回 {"state", "url", "host"}，不顯示時回 None。

      ok      — 有可用的 source_url，按鈕可點（連續失敗才會被標 broken）
      broken  — 有 source_url 但已失效，灰色不可點
      missing — 沒有 source_url，但規則書內容是我們自己掃描／處理的（有 whole_context），
                灰色不可點，說明沒有外部出處
      None    — 兩者皆無，沒什麼可說，整顆按鈕不顯示
    """
    with_url = [rb for rb in rulebooks if rb.source_url]
    for rb in with_url:
        if rb.source_url_status != "broken":
            host = urlparse(rb.source_url).netloc.removeprefix("www.")
            return {"state": "ok", "url": rb.source_url, "host": host}
    if with_url:
        return {"state": "broken", "url": "", "host": ""}
    if any(rb.whole_context for rb in rulebooks):
        return {"state": "missing", "url": "", "host": ""}
    return None


def content_rulebooks_for(edition):
    """
    flowchart / 講稿的內容歸屬規則書。

    flowchart 與講稿是站方產出、會自動在地化成介面語言的內容，跟規則書本身是哪
    一國語言無關。若只認某一本被挑中的規則書，同一版本掛了多本不同語言規則書時，
    挑中哪一本會隨介面語言浮動，於是「英文看得到、切成別的語言就 404」。所以這裡
    認的是這個版本底下的**所有**規則書；版本自己沒有規則書時，才退回同款遊戲其他
    版本的任一本。

    edition.rulebooks 已由 EditionDetailView.get_queryset() prefetch，所以有規則書
    的常見情況是 0 查詢。
    """
    own = list(edition.rulebooks.all())
    if own:
        return own

    from game.models import Rulebook
    fallback = Rulebook.objects.filter(
        edition__game=edition.game
    ).select_related('edition').first()
    return [fallback] if fallback else []


class EditionTabFlags(NamedTuple):
    has_flowchart: bool
    has_script: bool


def edition_tab_flags(edition, content_rulebooks):
    """
    分頁列要顯示哪幾顆按鈕。

    四個分頁各自是獨立頁面，所以每一頁都得知道「另外幾個分頁存不存在」才畫得出
    分頁列。這裡只做 EXISTS，不跑 EditionDetailView 那兩個完整建構（流程圖要
    deepcopy + 翻譯查詢 + 走訪整張圖，講稿要逐字元遮罩）。

    ⚠️ 判準必須與 EditionDetailView._flowchart_context / _script_context 一致，
    否則會出現「按鈕在、點進去 404」或「頁面渲染得出來、自己那顆按鈕卻不見」。
    改動任一邊都要同時改另一邊。
    """
    from game.models import RulebookFlowchart, RulebookScript

    base = Q(linked_editions=edition)
    if content_rulebooks:
        base |= Q(rulebook__in=content_rulebooks)

    # 已發布必然非空（核准時擋掉空圖），對應完整建構裡的 `if not effective: continue`。
    has_flowchart = RulebookFlowchart.objects.published().filter(base).exists()

    # effective_text = adjusted_text or script_text，所以「有講稿」＝兩者不同時為空
    has_script = RulebookScript.objects.filter(
        base, is_published=True,
    ).exclude(
        Q(adjusted_text__isnull=True) | Q(adjusted_text=""), script_text="",
    ).exists()

    return EditionTabFlags(has_flowchart, has_script)


def get_edition_flowchart(edition):
    """取這款遊戲人工核可過的流程圖 JSON，沒有就回 None。"""
    try:
        from game.models import RulebookFlowchart
        fc = RulebookFlowchart.objects.published().filter(
            rulebook__edition__game=edition.game,
        ).select_related("publication").order_by("display_order", "-initial", "ruleset").first()
        if fc:
            return fc.publication.content
    except Exception:
        pass
    return None


def get_edition_skills(game):
    """
    回傳 (has_skills, skills_dict)。六項能力全為 0/None 時 skills 為 None。
    """
    has_skills = bool(
        game.adaptability or game.collaboration or game.communication or
        game.creativity or game.critical_thinking or game.problem_solving
    )
    if not has_skills:
        return False, None
    return True, {
        "adaptability": game.adaptability or 0,
        "collaboration": game.collaboration or 0,
        "communication": game.communication or 0,
        "creativity": game.creativity or 0,
        "critical_thinking": game.critical_thinking or 0,
        "problem_solving": game.problem_solving or 0,
    }
