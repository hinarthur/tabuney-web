
from .models import Translation, Tribe
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.cache import cache
from rest_framework import status
from django.contrib.auth.models import User    
from translation.models import Tribe
from member.models import Member
from rest_framework.permissions import AllowAny, IsAdminUser
from django.conf import settings
from rest_framework.permissions import IsAdminUser
from django.utils import timezone

class TribeListView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        tribes = Tribe.objects.all().order_by('name')
        res = [
            {
                "code": tribe.language,       # 例如 'en'
                "label": tribe.name  # 例如 'English', 若無則拿 name
            }
            for tribe in tribes
        ]
        return Response(res)

class TranslationListView(APIView):
    permission_classes = [AllowAny] 
    def get(self, request):
        lang = request.query_params.get('lang', 'en')
        cache_key = f'translation_{lang}'
        data = cache.get(cache_key)
        if data is not None:
            print(f"[CACHE] cache HIT for {cache_key}")
            return Response(data)
        print(f"[CACHE] cache MISS for {cache_key}")
        try:
            tribe = Tribe.objects.get(language=lang)
        except Tribe.DoesNotExist:
            return Response({'error': 'Language not supported.'}, status=404)

        translations = Translation.objects.filter(tribe=tribe)
        res = {t.key: t.value for t in translations}
        cache.set(cache_key, res, timeout=60 * 60)  # 快取 1 hr，依需求調整
        return Response(res)
 
class GetLanguageView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        user = request.user
        if user.is_authenticated:
            try:
                member = Member.objects.get(id=user.id)
                if member.tribe and member.tribe.language:
                    return Response({"language": member.tribe.language}, status=status.HTTP_200_OK)
            except Member.DoesNotExist:
                pass  # 如果找不到 Member 記錄，返回預設語言
        # 對於未認證用戶或找不到語言設定的情況，返回預設語言 'en'
        return Response({"language": "en"}, status=status.HTTP_200_OK)
    

class SyncTranslationView(APIView):
    permission_classes = [IsAdminUser]  # 只限管理員

    def post(self, request):
        action = request.data.get('action', 'upsert')
        if action == 'delete':
            return self._delete(request)
        return self._upsert(request)

    def _delete(self, request):
        keys = request.data.get('keys', [])
        if not isinstance(keys, list) or not keys:
            return Response({'error': 'keys must be a non-empty list'}, status=400)
        try:
            deleted_count, _ = Translation.objects.filter(key__in=keys).delete()
            return Response({'result': 'ok', 'deleted': deleted_count})
        except Exception as e:
            return Response({'error': str(e)}, status=500)

    def _upsert(self, request):
        data = request.data.get('translations', [])
        if not isinstance(data, list):
            return Response({'error': 'translations must be a list'}, status=400)

        created = 0
        updated = 0
        try:
            for row in data:
                lang_code = row.get('language')
                key = row.get('key')
                value = row.get('value')
                if not lang_code or key is None or value is None:
                    continue

                try:
                    tribe = Tribe.objects.get(language=lang_code)
                except Tribe.DoesNotExist:
                    continue # 或者報錯也行，這邊先跳過

                obj, created_flag = Translation.objects.update_or_create(
                    tribe=tribe,
                    key=key,
                    defaults={
                        'value': value,
                        'is_synced': True,
                        'synced_at': timezone.now(),
                    }
                )
                if created_flag:
                    created += 1
                else:
                    updated += 1

            return Response({
                'result': 'ok',
                'count': created + updated,
                'created': created,
                'updated': updated,
            })
        except Exception as e:
            return Response({'error': str(e)}, status=500)