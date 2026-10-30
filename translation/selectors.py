"""
翻譯字串查詢，與 HTTP 無關。

網站的 template tag（{% t %}）與 API serializer 都需要「給語言碼與 key，拿字串」，
這裡是共用的入口。
"""


def get_translation(lang, key, default=''):
    """查單一翻譯字串。查不到（語言不存在、key 不存在）回 default。"""
    from translation.models import Tribe, Translation
    try:
        tribe = Tribe.objects.get(language=lang)
        return Translation.objects.get(tribe=tribe, key=key).value
    except Exception:
        return default


def get_translations(lang, keys):
    """一次查多個翻譯字串，回傳 {key: value}。

    查不到的 key 不會出現在回傳的 dict 裡 —— 呼叫端因此能用 `key in result` 分辨
    「沒這筆翻譯」與「翻譯是空字串」。逐一呼叫 get_translation 會是每個 key 兩個
    查詢，這裡固定兩個。
    """
    from translation.models import Tribe, Translation
    keys = list(keys)
    if not keys:
        return {}
    try:
        tribe = Tribe.objects.get(language=lang)
    except Exception:
        return {}
    rows = Translation.objects.filter(tribe=tribe, key__in=keys).values_list('key', 'value')
    return dict(rows)


def build_opening_message(lang, edition_name, chat_status):
    """
    依聊天狀態組出開場白。三種狀態各有自己的前後綴翻譯 key，
    中間夾遊戲名稱。
    """
    prefixes = {
        'matched': ('chat.opening.prefix', 'chat.opening.suffix'),
        'linked': ('chat.opening.alternative1', 'chat.opening.alternative2'),
        'not_ready': ('chat.opening.notready1', 'chat.opening.notready2'),
    }
    head_key, tail_key = prefixes.get(chat_status, prefixes['not_ready'])
    return get_translation(lang, head_key) + edition_name + get_translation(lang, tail_key)
