from django import template
from django.utils.safestring import mark_safe
from bs4 import BeautifulSoup

register = template.Library()


@register.filter
def demote_h1(value):
    """把抓取回來的文章內容中的 <h1> 降成 <h2>。

    頁面自身的 h1 是文章標題，內容裡的 h1 屬於來源網站的排版，
    兩者同時存在會讓一個頁面出現多個 h1（不利 SEO）。
    """
    if not value:
        return ''
    # 大多數文章內容不含 h1，先做便宜的字串檢查再決定要不要解析
    if '<h1' not in value.lower():
        return mark_safe(value)
    soup = BeautifulSoup(value, 'html.parser')
    for tag in soup.find_all('h1'):
        tag.name = 'h2'
    return mark_safe(str(soup))
