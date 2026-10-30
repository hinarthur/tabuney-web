"""FAQ 頁的題目結構，給 FAQPage 結構化資料用。

問答文字本身在 DB（translation.Translation），模板靠 {% t %} 一題一題取。JSON-LD
要在 Python 層組同一批內容，所以題目清單得在模板之外再存在一份 —— 兩邊會漂開，
由 home/tests.py 的 test_faq_items_match_template 擋著。
"""

# 與 templates/faq.html 的 <details> 一一對應，順序相同。
# 新增／移除題目時兩邊都要改。
FAQ_ITEMS = [
    "publisher",
    "languages",
    "game_not_found",
    "game_suggest",
    "free",
    "rulesbot",
    "rulesbot_difference",
    "rulesbot_accuracy",
    "content_ai",
    "flowchart",
    "script",
    "collection",
    "privacy",
    "deleteaccount",
]

# rulesbot_difference 的答案在模板裡是一張比較表（faq.html:62-91），沒有單一
# faq.rulesbot_difference.answer。這裡記下表格佈局，好把它攤平成一段純文字答案。
# headers[0] 是列標籤那一欄的表頭，不進答案文字；每列的 row[0] 是列標籤。
COMPARISON_ITEM = "rulesbot_difference"
COMPARISON_TABLE = {
    "headers": ["comparison", "rulesbot", "generalai"],
    "rows": [
        ["game_covered", "limited", "broad"],
        ["basis", "rulebook_only", "mix"],
        ["hallucination", "less_likely", "more_likely"],
    ],
}


def _key(item, suffix):
    return f"faq.{item}.{suffix}"


def _comparison_key(cell):
    return f"faq.{COMPARISON_ITEM}.answer.{cell}"


def translation_keys():
    """這一頁組 JSON-LD 需要的所有翻譯 key，餵給 get_translations 一次查完。"""
    keys = []
    for item in FAQ_ITEMS:
        keys.append(_key(item, "question"))
        if item != COMPARISON_ITEM:
            keys.append(_key(item, "answer"))
    keys.extend(_comparison_key(h) for h in COMPARISON_TABLE["headers"])
    for row in COMPARISON_TABLE["rows"]:
        keys.extend(_comparison_key(cell) for cell in row)
    return keys


def _comparison_answer(strings):
    """把比較表攤平成純文字。任一格缺翻譯就整段放棄 —— 半張表比沒有更糟。

    刻意不重建 <table> 標記：那份 HTML 已經在模板裡了，複製一份到 Python
    等於兩處維護，而 schema.org 的 Answer.text 吃純文字沒有損失。
    """
    headers = [strings.get(_comparison_key(h)) for h in COMPARISON_TABLE["headers"]]
    if not all(headers):
        return ""

    lines = []
    for row in COMPARISON_TABLE["rows"]:
        cells = [strings.get(_comparison_key(c)) for c in row]
        if not all(cells):
            return ""
        pairs = "; ".join(
            f"{header} — {value}" for header, value in zip(headers[1:], cells[1:])
        )
        lines.append(f"{cells[0]}: {pairs}")
    return ". ".join(lines) + "."


def build_questions(strings):
    """由翻譯字典組出 [(問題, 答案), ...]，順序同 FAQ_ITEMS。

    問題或答案任一缺翻譯就整題跳過 —— 模板的 {% t %} 查無資料時會直接印出 key，
    那種字串進了 JSON-LD 會變成一題名叫 "faq.publisher.question" 的 Question。
    """
    questions = []
    for item in FAQ_ITEMS:
        question = strings.get(_key(item, "question"), "").strip()
        if item == COMPARISON_ITEM:
            answer = _comparison_answer(strings)
        else:
            answer = strings.get(_key(item, "answer"), "").strip()
        if question and answer:
            questions.append((question, answer))
    return questions
