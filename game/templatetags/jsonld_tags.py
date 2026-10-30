from django import template
from django.utils.safestring import mark_safe

from game.structured_data import dump_jsonld, graph_jsonld

register = template.Library()


@register.simple_tag
def jsonld_graph(*node_lists):
    """把全站節點（context processor）與頁面節點（view）合併成單一 @graph <script>。

    需要在 template 層合併是因為 context processor 是 render 時才執行的，
    看不到 view 的 context —— 兩邊的節點沒辦法在 Python 層先併好。

    同一個 @id 出現多次時後者勝出：這讓 view 能覆寫全站預設的節點（例如版本詳情頁
    要在自己的 WebPage 上補 about，/about/ 要把 WebPage 換成 AboutPage），
    而不會在圖裡留下兩個 @id 相同、內容不同的節點。
    沒有 @id 的節點（BreadcrumbList）一律保留。
    """
    merged = []
    positions = {}

    for node_list in node_lists:
        if not node_list:
            continue
        for node in node_list:
            if not node:
                continue
            node_id = node.get("@id")
            if node_id and node_id in positions:
                merged[positions[node_id]] = node
                continue
            if node_id:
                positions[node_id] = len(merged)
            merged.append(node)

    graph = graph_jsonld(merged)
    if not graph:
        return ''
    return mark_safe(
        f'<script type="application/ld+json">{dump_jsonld(graph)}</script>'
    )
