"""
/api/v1/ — 給 App 用的 JSON 端點。

這裡刻意保持很薄：查詢在 game/selectors.py、序列化在 game/serializers.py，
網站的 HTML view 呼叫的是同一份。新增端點時請維持這個形狀，不要把查詢邏輯寫回 view。
"""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from game.models import Edition
from game.selectors import annotate_editions, featured_editions, search_editions
from game.serializers.edition_serializers import (
    EditionCardSerializer,
    EditionDetailSerializer,
)
from stats.utils import log_search, log_view

PAGE_SIZE = 20
FEATURED_SIZE = 6


class EditionSearchAPIView(APIView):
    """
    GET /api/v1/games/?q=<關鍵字>&offset=<位移>

    無 q 時回傳隨機精選（featured=true）。
    搜尋是冪等讀取，所以用 GET 而非舊版的 POST。
    """

    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get('q', '').strip()

        try:
            offset = max(0, int(request.query_params.get('offset', 0)))
        except (TypeError, ValueError):
            offset = 0

        if not query:
            editions = annotate_editions(list(featured_editions(FEATURED_SIZE)))
            return Response({
                'results': EditionCardSerializer(editions, many=True).data,
                'next': False,
                'total': len(editions),
                'featured': True,
            })

        result = search_editions(query)
        total = result.editions.count()
        log_search(
            request, query, 'edition', source='app',
            result_count=total, matched_by=result.matched_by,
        )
        editions = annotate_editions(list(result.editions[offset: offset + PAGE_SIZE]))

        return Response({
            'results': EditionCardSerializer(editions, many=True).data,
            'next': (offset + len(editions)) < total,
            'total': total,
            'featured': False,
        })


class EditionDetailAPIView(APIView):
    """GET /api/v1/games/<uuid>/?lang=<語言碼>"""

    permission_classes = [AllowAny]

    def get(self, request, pk):
        edition = (
            Edition.objects.select_related('game')
            .filter(pk=pk)
            .first()
        )
        if edition is None:
            return Response({'detail': 'Not found.'}, status=404)

        log_view(request, edition)
        lang = getattr(request, 'lang', 'en')
        data = EditionDetailSerializer(edition, context={'lang': lang}).data
        return Response(data)
