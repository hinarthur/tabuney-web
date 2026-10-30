
from django.utils.translation import gettext as _

class LanguageView(APIView):
    def post(self, request):
        language = request.data.get('language')
        # 切換語言邏輯
        translation.activate(language)
        return Response({'status': 'success'})