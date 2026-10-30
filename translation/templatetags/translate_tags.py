# translation/templatetags/translate_tags.py
from django import template
from django.utils.safestring import mark_safe
from translation.models import Translation

register = template.Library()


def _lang_table(request, lang):
    """
    該語言的 {key: value}，每個請求只查一次並掛在 request 上。
    原本每個 {% t %} 各查 Tribe + Translation 兩次，一頁幾十個 tag 就是上百次查詢
    （VPS 上 translation_tribe 6 天被全表掃描 6700 萬次）。一個語言約 400 筆、30KB，整包載入很便宜。
    """
    tables = getattr(request, '_t_tables', None)
    if tables is None:
        tables = request._t_tables = {}
    if lang not in tables:
        tables[lang] = dict(
            Translation.objects.filter(tribe__language=lang).values_list('key', 'value')
        )
    return tables[lang]


@register.simple_tag(takes_context=True)
def t(context, key):
    request = context.get('request')
    if not request:
        return key

    lang = getattr(request, 'lang', 'en')

    # 語言不存在或 key 不存在都回 key（與原本 DoesNotExist 的行為一致）
    value = _lang_table(request, lang).get(key)
    if value is None:
        return key
    return mark_safe(value)  # ← 加 mark_safe