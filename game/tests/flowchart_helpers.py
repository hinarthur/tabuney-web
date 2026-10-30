"""測試用：直接把流程圖目前的草稿設成公開版（跳過審核流程與權限檢查）。"""

from django.utils import timezone

from game.models import FlowchartPublication


def publish_flowchart(chart, content=None):
    """建立／覆寫 chart 的公開快照；content 省略時用目前草稿。"""
    from game.models import flowchart_content_hash

    content = content if content is not None else chart.effective_json
    pub, _ = FlowchartPublication.objects.update_or_create(
        flowchart=chart,
        defaults=dict(
            content=content,
            content_hash=flowchart_content_hash(content),
            is_live=True,
            approved_by_name="test",
            approved_at=timezone.now(),
        ),
    )
    return pub
