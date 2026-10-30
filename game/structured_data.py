"""
Schema.org 結構化資料（JSON-LD）。

每頁輸出單一 @graph（見 graph_jsonld），節點之間靠 @id 互相引用：

    {SITE_URL}/#organization    全站組織，所有 author / publisher 都指向它
    {SITE_URL}/#website         全站
    {page_url}#webpage          每一頁，author 掛在這裡
    {edition_url}#game          版本詳情頁的遊戲本體

因此各函式回傳的是「不含 @context 的節點」，@context 由 graph_jsonld() 統一補在
最外層 —— 節點若各自帶 @context，合併進 @graph 後會變成非法的巢狀 context。

輸出一律走 dump_jsonld()，它會把 < 之類的字元轉成 \\u003c —— 遊戲名稱是使用者
可控的資料，直接字串串接進 <script> 會被 </script> 打斷並注入。
（作法與 Django 內建的 json_script 相同。）
"""

import json

from django.conf import settings
from django.utils import translation
from django.utils.safestring import mark_safe

# 組織的站外檔案連結（BGG guild、社群帳號、商店頁等）。AI 回答引擎靠 sameAs 交叉
# 驗證「這個組織真實存在」，是信任訊號裡最重的一項。目前 Tabuney 沒有站外公開帳號，
# 所以留空 —— 填一個指回自己網站的連結不構成驗證，只會稀釋節點。開帳號後補進來即可。
ORG_SAME_AS = []

# Organization.knowsAbout：宣告專業領域。AI 引擎判斷「這站有沒有資格談這個主題」時會讀。
ORG_KNOWS_ABOUT = [
    "Board games",
    "Tabletop game rules",
    "Game master facilitation",
]


def dump_jsonld(data):
    """序列化成可安全嵌進 <script> 的 JSON。"""
    if not data:
        return ""
    text = json.dumps(data, ensure_ascii=False)
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return mark_safe(text)


def graph_jsonld(nodes):
    """把節點清單包成單一 @graph。"""
    nodes = [n for n in nodes if n]
    if not nodes:
        return None
    return {"@context": "https://schema.org", "@graph": nodes}


def org_id(site_url):
    return f"{site_url}/#organization"


def org_ref(site_url):
    """author / publisher 統一走這個引用，組織節點整張圖只定義一次。"""
    return {"@id": org_id(site_url)}


def website_id(site_url):
    return f"{site_url}/#website"


def _entity_nodes(entities):
    """把 EditionRole 上的 Entity 轉成 Person / Organization 節點。"""
    nodes = []
    for entity in entities:
        if not entity or not entity.name:
            continue
        node = {
            "@type": "Person" if entity.entity_type == "individual" else "Organization",
            "name": entity.name,
        }
        if entity.website:
            node["sameAs"] = entity.website
        nodes.append(node)
    return nodes


def edition_jsonld(edition, request, site_url, tab=None, tab_name=None):
    """一款桌遊版本的 Game + BreadcrumbList 結構化資料。

    tab / tab_name 有值時，麵包屑補上第三層（分頁本身）。四個分頁是四個獨立頁面，
    麵包屑要走到讀者實際所在的那一層，否則三個分頁的麵包屑會全部停在版本頁。
    tab_name 由呼叫端依介面語言取好再傳進來——這個模組刻意不碰 request 與翻譯。

    creator / illustrator 是「這款遊戲」的創作者。這一頁本身的 author 不是他們而是
    Tabuney —— 頁面主體是站方產出的 flowchart、GM 講稿與 Rulesbot，那部分掛在
    webpage_jsonld() 的節點上。兩者混用等於把站方的原創產出記到設計師名下。
    """
    game = edition.game
    name = edition.name or game.canonical_name

    # 麵包屑跟著讀者當下的語言走。
    page_url = site_url + edition.get_absolute_url()

    # Game 是跨語言唯一的實體，@id 不能隨語言前綴浮動 —— 否則同一款遊戲在 6 種語言下
    # 會被當成 6 個不同的 Game。固定用預設語言（無前綴）的網址當正規識別。
    with translation.override(settings.LANGUAGE_CODE):
        game_url = site_url + edition.get_absolute_url()

    node = {
        "@type": "Game",
        "@id": game_url + "#game",
        "name": name,
        "url": game_url,
    }

    if edition.summary:
        node["description"] = edition.summary
    if edition.thumbnail:
        node["image"] = site_url + edition.thumbnail.url
    if edition.release_year:
        node["datePublished"] = str(edition.release_year)
    if edition.updated_at:
        node["dateModified"] = edition.updated_at.date().isoformat()
    if edition.age:
        node["typicalAgeRange"] = f"{edition.age}-"

    if game.min_players or game.max_players:
        node["numberOfPlayers"] = {
            "@type": "QuantitativeValue",
            "minValue": game.min_players,
            "maxValue": game.max_players,
        }

    if game.min_playtime or game.max_playtime:
        node["timeRequired"] = f"PT{game.max_playtime or game.min_playtime}M"

    designers = _entity_nodes(edition.designer_entities)
    if designers:
        node["creator"] = designers

    artists = _entity_nodes(edition.artist_entities)
    if artists:
        node["illustrator"] = artists

    publishers = _entity_nodes(edition.publisher_entities)
    if publishers:
        node["publisher"] = publishers

    items = [
        {"@type": "ListItem", "position": 1, "name": "Tabuney", "item": site_url + "/"},
        {"@type": "ListItem", "position": 2, "name": name, "item": page_url},
    ]
    if tab and tab_name:
        items.append({
            "@type": "ListItem", "position": 3,
            "name": tab_name, "item": f"{page_url}{tab}/",
        })

    breadcrumb = {"@type": "BreadcrumbList", "itemListElement": items}

    return [node, breadcrumb]


def flowchart_howto_jsonld(url, name, outline, about_id=None):
    """流程圖分頁的 HowTo 節點：把文字版大綱攤成 HowToSection / HowToStep。

    來源就是頁面上那份 partials/flowchart_textview.html 用的同一個 outline，所以
    結構化資料與可見文字完全一致，不是另外生出來的隱藏內容。付費鎖住的 ruleset
    其 outline 本來就是 None（見 EditionDetailView._flowchart_context），不會走到
    這裡，付費內容不會從結構化資料外洩。

    outline 沒有任何 phase 時回傳 None：一個空 step 的 HowTo 比沒有更糟。
    """
    if not outline:
        return None

    sections = []
    for phase in outline.get("phases") or []:
        steps = [
            {"@type": "HowToStep", "position": i, "name": s["label"]}
            for i, s in enumerate(phase.get("steps") or [], start=1)
            if s.get("label")
        ]
        if not steps:
            continue
        sections.append({
            "@type": "HowToSection",
            "position": len(sections) + 1,
            "name": phase.get("label") or "",
            "itemListElement": steps,
        })

    if not sections:
        return None

    node = {
        "@type": "HowTo",
        "@id": f"{url}#howto",
        "name": name,
        "url": url,
        "step": sections,
    }
    if about_id:
        node["about"] = {"@id": about_id}
    return node


def script_article_jsonld(site_url, url, headline, locked, about_id=None):
    """GM 講稿分頁的 Article 節點。

    刻意不放 articleBody：講稿是付費內容。未達訂閱等級時再加上 Google 對付費牆
    內容的標準標記（isAccessibleForFree + hasPart/cssSelector），讓爬蟲知道看到
    的是預覽而不是全文——少了這個標記，「爬蟲看到的內容比讀者少」會被當成 cloaking。
    """
    node = {
        "@type": "Article",
        "@id": f"{url}#article",
        "url": url,
        "author": org_ref(site_url),
        "publisher": org_ref(site_url),
    }
    if headline:
        node["headline"] = headline
    if about_id:
        node["about"] = {"@id": about_id}

    if locked:
        node["isAccessibleForFree"] = False
        node["hasPart"] = {
            "@type": "WebPageElement",
            "isAccessibleForFree": False,
            "cssSelector": ".script-pane",
        }
    else:
        node["isAccessibleForFree"] = True

    return node


def organization_jsonld(site_url, logo_url, description, contact_url=None,
                        principles_url=None):
    """全站品牌 Organization 結構化資料，出現在每一頁。

    principles_url 指向「內容與發布原則」頁。在沒有 sameAs（站外交叉驗證）的情況下，
    這是少數不依賴外部平台、又能真的加分的 E-E-A-T 訊號 —— 對一個內容部分由 AI
    生成的資料站來說，講清楚生成與審核流程本身就是可信度的一部分。
    """
    node = {
        "@type": "Organization",
        "@id": org_id(site_url),
        "name": "Tabuney",
        # 固定值：確保不論 seo.default.description 之後怎麼改，都帶得到 "board game" 關鍵字
        "alternateName": "Tabuney - Board Game Database",
        "url": site_url + "/",
        "logo": logo_url,
        "description": description,
        "knowsAbout": ORG_KNOWS_ABOUT,
    }

    if ORG_SAME_AS:
        node["sameAs"] = ORG_SAME_AS

    if contact_url:
        node["contactPoint"] = {
            "@type": "ContactPoint",
            "contactType": "customer support",
            "url": contact_url,
        }

    if principles_url:
        node["publishingPrinciples"] = principles_url

    return node


def website_jsonld(site_url, search_path=None):
    """全站 WebSite 節點，每頁的 WebPage 都用 isPartOf 指向它。

    search_path 有值時才加 SearchAction（讓 Google 可能顯示站內搜尋框）。
    只有無查詢的搜尋落地頁會傳 —— 搜尋結果頁是 noindex 的，而 SearchAction 的
    urlTemplate 帶著 {search_term_string} 字面，掛得越廣爬蟲把它當關鍵字送回來的機會越多
    （stats/utils.py 的 _is_bot 就是在擋這個）。
    """
    node = {
        "@type": "WebSite",
        "@id": website_id(site_url),
        "name": "Tabuney",
        "url": site_url + "/",
        "publisher": org_ref(site_url),
    }

    if search_path:
        node["potentialAction"] = {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{site_url}{search_path}?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        }

    return node


def webpage_jsonld(site_url, url, page_type="WebPage", about_id=None):
    """每一頁的 WebPage 節點 —— author 就掛在這裡。

    name 刻意不填：頁面標題是 template block，context processor 取不到，
    而 schema.org 不強制 WebPage.name。
    """
    node = {
        "@type": page_type,
        "@id": f"{url}#webpage",
        "url": url,
        "isPartOf": {"@id": website_id(site_url)},
        "author": org_ref(site_url),
        "publisher": org_ref(site_url),
    }

    if about_id:
        node["about"] = {"@id": about_id}

    return node


def faq_jsonld(site_url, url, questions):
    """FAQ 頁的 FAQPage 節點，mainEntity 掛著每一組問答。

    questions 是 [(問題, 答案), ...]。@id 沿用 webpage_jsonld 的 {url}#webpage ——
    jsonld_graph 靠同 @id 覆寫，這個節點才會取代 context processor 放的通用 WebPage
    而不是在圖裡多出第二個。

    沒有任何問答時回傳 None：這頁翻譯還沒進 DB 的話，一個空 mainEntity 的 FAQPage
    比退回普通 WebPage 更糟。graph_jsonld 會把 None 濾掉。
    """
    if not questions:
        return None

    node = webpage_jsonld(site_url, url, page_type="FAQPage")
    node["mainEntity"] = [
        {
            "@type": "Question",
            "name": question,
            "acceptedAnswer": {"@type": "Answer", "text": answer},
        }
        for question, answer in questions
    ]
    return node
