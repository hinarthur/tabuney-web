#feed/views.py
from django.conf import settings
from django.core.management import call_command
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_q.models import Schedule, Task
from django_q.tasks import schedule
from django_q.models import Schedule as QSchedule
from django.db.models import Count
from django.db.models import Subquery, OuterRef

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets, generics, serializers
from rest_framework.permissions import IsAdminUser, IsAuthenticated, AllowAny
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, NotFound

import os
from dotenv import load_dotenv
load_dotenv()  # 讀取 .env 文件
from datetime import timedelta, datetime
from feed.models import Rss
from collections import defaultdict
import requests
from bs4 import BeautifulSoup
import feedparser
from urllib.parse import urljoin, urlparse

from member.models import Member
from translation.models import Tribe
from .models import Work, WorkTranslation, SavedWork, WorkLabel
from .serializers import WorkSerializer, SavedWorkSerializer, WorkLabelSerializer

from feed.services.rss_service import discover_rss
from feed.services.work_service import mark_irrelevant
from feed.services.bookmark_service import save_work


def _get_all_tribe_languages():
    """回傳所有有 language 的 Tribe 的 language code 列表"""
    return list(
        Tribe.objects.filter(language__isnull=False)
        .exclude(language='')
        .values_list('language', flat=True)
        .order_by('language')
    )

class FeedListView(APIView):
    permission_classes = [AllowAny]
    def get(self, request, *args, **kwargs):
        offset = int(request.query_params.get("offset", 0))
        limit = int(os.getenv("LOADING_BATCH", 10))  # 默认批次大小为 10
        languages_str = request.query_params.get("languages", "").strip()
        if languages_str:
            languages = [x.strip() for x in languages_str.split(',') if x.strip()]
        else:
            languages = _get_all_tribe_languages()
        if not languages:
            languages = ['de', 'en', 'es', 'fr', 'ja', 'zh']  # fallback
        # works = Work.objects.filter(lang__in=languages).order_by('-publishdate')[offset:offset + limit]
        works = Work.objects.filter(
            lang__in=languages,
            irrelevant=0
        # ).order_by('-publishdate')[offset:offset + limit]
        ).select_related('rss').order_by('-publishdate')[offset:offset + limit]
        
        data = []

        for work in works:
            rss = work.rss 
            logo_url = None
            if rss.logo:
                # logo_path = rss.logo.name
                # if not logo_path.startswith('sitelogo/'):
                #     logo_path = f'sitelogo/{logo_path}'
                # logo_url = request.build_absolute_uri(settings.MEDIA_URL + logo_path)
                logo_url = request.build_absolute_uri(rss.logo.url)

            data.append({
                'id': work.id,
                'title': work.title,
                'url': work.url,
                'image': work.image,
                'publishdate': work.publishdate,
                'content': work.content,
                'preview': work.preview, 
                # 'rssLogo': logo_url if rss.logo else None,  # 获取 logo 的 URL
                'rssLogo': logo_url,
                'rssSitename': rss.sitename,  # 获取站点名称
            })

        return Response(data)


class FeedFilterConfigView(APIView):
    """取得 filter modal 需要的 tribes 與使用者的 feedlist_lang"""
    permission_classes = [AllowAny]

    def get(self, request):
        ready_langs = [code for code, _ in settings.LANGUAGES]
        tribes = Tribe.objects.filter(language__in=ready_langs).order_by('name')
        tribes_data = [{"code": t.language, "label": t.name} for t in tribes]

        feedlist_lang = None
        if request.user.is_authenticated:
            try:
                member = request.user.member
                feedlist_lang = list(member.feedlist_lang) if member.feedlist_lang else []
            except (AttributeError, Member.DoesNotExist):
                feedlist_lang = []

        return Response({
            "tribes": tribes_data,
            "feedlist_lang": feedlist_lang,
            "is_authenticated": request.user.is_authenticated,
        })


class SaveFeedlistLangView(APIView):
    """儲存使用者的 feedlist_lang"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        languages = request.data.get("languages", [])
        if not isinstance(languages, list):
            return Response({"detail": "languages must be an array"}, status=status.HTTP_400_BAD_REQUEST)

        member = request.user.member
        ready_langs = {code for code, _ in settings.LANGUAGES}
        valid_codes = set(
            Tribe.objects.filter(language__in=languages)
            .values_list("language", flat=True)
        ) & ready_langs
        member.feedlist_lang = [c for c in languages if c in valid_codes]
        member.save()

        return Response({"feedlist_lang": member.feedlist_lang})


class FeedBookmarkView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, *args, **kwargs):
        current_member = request.user.member
        offset = int(request.query_params.get("offset", 0))
        limit = int(os.getenv("LOADING_BATCH", 10))  # 默认批次大小为 10
        labelId = int(request.query_params.get("labelId", 0))
        # languages_str = request.query_params.get("languages", "en,zh,ja")
        # languages = languages_str.split(',') if languages_str else ['en', 'zh', 'ja']
        # works = Work.objects.filter(
        #     # lang__in=languages,
        #     # irrelevant=0
        # ).order_by('-publishdate')[offset:offset + limit]
        if labelId != 0:            
            saved_works = SavedWork.objects.filter(
                member=current_member, label=labelId
            ).select_related('work').order_by('-saved_at')[offset:offset + limit]
        else:          
            # saved_works = SavedWork.objects.filter(
            #     member=current_member
            # ).select_related('work').order_by('-saved_at')[offset:offset + limit]
            
            subquery = SavedWork.objects.filter(
                member=current_member,
                work=OuterRef('work')
            ).order_by('-saved_at')

            tmp_saved_works = SavedWork.objects.filter(
                member=current_member
            ).annotate(
                latest_saved_at=Subquery(
                    SavedWork.objects.filter(
                        member=current_member,
                        work=OuterRef('work')
                    ).order_by('-saved_at').values('saved_at')[:1]
                )
            ).order_by('work', '-latest_saved_at').distinct('work')

            # 然後再做 slicing
            saved_works = tmp_saved_works[offset:offset + limit]
            
        # 從 SavedWork 實例中提取 Work 對象
        # 這裡會得到一個 Work 對象的列表
        works = [saved_work.work for saved_work in saved_works]
        # 使用 WorkSerializer 序列化這些 Work 對象
        # many=True 表示我們正在序列化一個對象列表
        # serializer = WorkSerializer(works, many=True)

        # return Response(serializer.data, status=status.HTTP_200_OK)
        
        data = []

        for work in works:
            rss = work.rss 
            logo_url = None
            if rss.logo:
                logo_path = rss.logo.name
                if not logo_path.startswith('sitelogo/'):
                    logo_path = f'sitelogo/{logo_path}'
                logo_url = request.build_absolute_uri(settings.MEDIA_URL + logo_path)
            # 获取翻译后的标题
            # translation = work.translations.filter(language=user_language).first()
            # title = translation.translated_title if translation else work.title

            data.append({
                'id': work.id,
                'title': work.title,
                'url': work.url,
                'image': work.image,
                'publishdate': work.publishdate,
                'content': work.content,
                'rssLogo': logo_url if rss.logo else None,  # 获取 logo 的 URL
                'rssSitename': rss.sitename,  # 获取站点名称
            })

        return Response(data)    
  
class FetchRssView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        try:
            # 使用 call_command 的詳細模式
            from io import StringIO
            out = StringIO()
            err = StringIO()
            call_command('fetch_rss', stdout=out, stderr=err)
            # 檢查輸出
            stdout_content = out.getvalue()
            stderr_content = err.getvalue()
            print("STDOUT:", stdout_content)
            print("STDERR:", stderr_content)
            # call_command('fetch_rss')
            return Response({
                'status': 'success', 
                'message': 'RSS feeds fetched successfully'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'status': 'error', 
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ResetRssTasksView(APIView):   
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]  # 只允許管理員操作

    def post(self, request, *args, **kwargs):
        try:
            # 刪除所有 Fetch RSS 的排程與任務
            Schedule.objects.filter(name__startswith="Fetch RSS").delete()
            Task.objects.all().delete()

            rss_feeds = Rss.objects.all()
            total_feeds = rss_feeds.count()

            if total_feeds == 0:
                return Response({'message': 'No RSS feeds found to schedule.'}, status=status.HTTP_200_OK)

            now = timezone.now()
            # Step1: 先把所有 feeds 按 frequency + lastfetch 計算分到將來哪一天要 schedule
            feeds_by_date = defaultdict(list)
            scheduled_feeds = 0  # 新增計數器，計算實際被排程的 feed 數量
            for rss_feed in rss_feeds:
                # 新增條件：如果 publish_frequency > 300，則跳過此 feed 不進行排程
                if rss_feed.publish_frequency > 300:
                    continue
                
                # 預計的下次執行間隔天數(1 ~ 22)
                fetch_interval_days = min(22, max(1, round(rss_feed.publish_frequency * 0.7)))
                # 按 lastfetch 計算下一次
                if rss_feed.lastfetch:
                    next_run = rss_feed.lastfetch + timedelta(days=fetch_interval_days)
                else:
                    next_run = now + timedelta(days=fetch_interval_days)
                # 拿掉時分秒，只記日期
                run_date = next_run.date()
                feeds_by_date[run_date].append((rss_feed, fetch_interval_days, next_run))
                scheduled_feeds += 1  # 增加計數器
            
            # Step2: 針對每個將來的 date 去平均分布 time（hh:mm）
            for run_date, feed_tuples in feeds_by_date.items():
                count_today = len(feed_tuples)
                # print('count_today::', count_today)
                # interval_minutes = 1440 // count_today if count_today > 0 else 0
                interval_minutes = 1440 / count_today  # 用浮點數
                start_time = datetime.combine(run_date, datetime.min.time()).replace(
                    tzinfo=timezone.get_current_timezone()
                )
                # 決定排序以便固定分配
                feed_tuples_sorted = sorted(feed_tuples, key=lambda x: x[0].id)
                # for idx, (rss_feed, fetch_interval_days, planned_next_run) in enumerate(feed_tuples_sorted):
                #     # 分布具體小時／分鐘
                #     hour = (idx * interval_minutes) // 60
                #     minute = (idx * interval_minutes) % 60
                #     # 用 run_date 組出 next_run
                #     next_run = datetime.combine(run_date, datetime.min.time()).replace(
                #         hour=hour, minute=minute, second=0, microsecond=0, tzinfo=timezone.get_current_timezone()
                #     )
                for idx, (rss_feed, fetch_interval_days, planned_next_run) in enumerate(feed_tuples_sorted):
                    minutes = round(idx * interval_minutes)
                    next_run = start_time + timedelta(minutes=minutes)
                    # print(f"{rss_feed}: {next_run.strftime('%Y-%m-%d %H:%M:%S %z')}")
                    # 避免出現在過去
                    if next_run < now:
                        next_run = now + timedelta(minutes=1)

                    task_name = f"Fetch RSS {rss_feed.id}"
                    schedule(
                        'feed.tasks.fetch_one_rss',  # 替換成你的任務函數
                        rss_feed.id,
                        name=task_name,
                        schedule_type=QSchedule.MINUTES,
                        minutes=fetch_interval_days * 24 * 60,  # 周期
                        repeats=-1,
                        next_run=next_run
                    )
                  
            print(f"RSS tasks reset successfully for {scheduled_feeds} feeds out of {total_feeds} total feeds.")
            return Response({
                'message': f'RSS tasks successfully reset and rescheduled for {scheduled_feeds} feeds out of {total_feeds} total feeds based on publish frequency and 24hr time spreading.'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error occurred: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
 
class WorkViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    queryset = Work.objects.all()
    serializer_class = WorkSerializer
    # print('getting work')

    @action(detail=True, methods=['post'])
    def irrelevant(self, request, pk=None):
        print('irrelevant work')
        work = self.get_object()
        # work.irrelevant += 1
        # work.save()
        # work.rss.total_irrelevant += 1
        # work.rss.save()
        mark_irrelevant(work)
        return Response({'irrelevant': work.irrelevant, 'total_irrelevant': work.rss.total_irrelevant})
    

class AddRssView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        print("Current user:", request.user)
        url = request.data.get('url')
        if not url:
            # return Response({'detail':'Please enter a valid website or RSS URL, such as example.com.'}, status=status.HTTP_400_BAD_REQUEST)
            return Response({
                'error': 'URL_EMPTY'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 自動補全 http(s) prefix
        if not urlparse(url).scheme:
            url = "https://" + url
            
        # 嘗試找出RSS
        rss_url, site_name, site_lang, site_logo = self.find_rss_info(url)
        if rss_url is None:
            # return Response({'detail': '未找到RSS，請確認網址或直接輸入RSS URL'}, status=status.HTTP_400_BAD_REQUEST)
            return Response({
                'error': 'RSS_NOT_FOUND'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 獲取當前會員
        try:
            member = Member.objects.get(id=request.user.id)
        except Member.DoesNotExist:
            member = None  # 如果會員不存在，設為 None（視需求調整）
            
        # 嘗試寫入DB
        rss_obj, created = Rss.objects.get_or_create(
            rss=rss_url,
            defaults={
                'sitename': site_name,
                'website': url,
                'lang': site_lang,
                'logo': None,  # 可以自行下載logo存檔，也可直接存logo url
                'status': 'user',
                'recommender': member,
            }
        )
        
        ## shhh... 別讓他知道
        # if not created:
        #     return Response({'detail': '此RSS已存在'}, status=status.HTTP_400_BAD_REQUEST)

        # return Response({'detail': 'RSS已加入，等待審核！'})
        return Response({
            'created': True,
        }, status=status.HTTP_201_CREATED)

    def find_rss_info(self, url):

        # 1. 直接判斷是不是RSS
        feed = feedparser.parse(url)
        if feed.bozo == 0 and feed.feed:
            return url, feed.feed.get('title'), feed.feed.get('language'), None

        # 2. 解析網站HTML尋找 RSS 連結（應該加 rel="alternate" 判斷）
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(resp.content, 'html.parser')
            # 取出所有 <link rel="alternate" type="application/rss+xml">
            # feed_links = soup.find_all('link', rel=lambda v: v and 'alternate' in v.lower(), type='application/rss+xml')
            feed_links = soup.find_all('link', type=['application/rss+xml', 'application/atom+xml'])
            for link in feed_links:
                rss_url = link.get('href')
                print('rss_url::', rss_url)
                if rss_url:
                    rss_url = urljoin(url, rss_url)
                    feed = feedparser.parse(rss_url)
                    if feed.bozo == 0 and feed.feed:
                        site_name = feed.feed.get('title')
                        site_lang = feed.feed.get('language')
                        logo = (feed.feed.get('image', {}).get('href')
                                if 'image' in feed.feed
                                else None)
                        return rss_url, site_name, site_lang, logo
        except Exception as e:
            pass
        return None, None, None, None
    
# 

class SaveWorkNoLabelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        member = request.user.member
        work_id = request.data.get('work')
        label_id = request.data.get('label')

        saved = save_work(
            member=member,
            work_id=work_id,
            label_id=label_id
        )

        if saved is None:
            return Response({'detail': 'Already saved'}, status=200)

        return Response(
            SavedWorkSerializer(saved).data,
            status=201
        )
    
class WorkLabelViewSet(viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication]
    serializer_class = WorkLabelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # get current member
        try:
            print('getting labels')
            member = Member.objects.get(id=self.request.user.id)
        except Member.DoesNotExist:
            return WorkLabel.objects.none()
        # return WorkLabel.objects.filter(member=member).order_by('id')
        return WorkLabel.objects.filter(member=member).annotate(
            saved_work_count=Count('saved_works') # 為每個 WorkLabel 實例添加一個 'saved_work_count' 屬性
        ).order_by('id')

    def perform_create(self, serializer):
        try:
            member = Member.objects.get(id=self.request.user.id)
        except Member.DoesNotExist:
            raise PermissionDenied("尚未註冊成會員")

        limit = member.limit('max_bookmark_category')
        if limit != -1 and WorkLabel.objects.filter(member=member).count() >= limit:
            raise PermissionDenied(f"已達分類數量上限（{limit}）")

        serializer.save(member=member)

    def perform_update(self, serializer):
        instance = serializer.instance
        member = Member.objects.get(id=self.request.user.id)
        if instance.member != member:
            raise PermissionDenied("無權限編輯此標籤")
        serializer.save()

    def perform_destroy(self, instance):
        member = Member.objects.get(id=self.request.user.id)
        if instance.member != member:
            raise PermissionDenied("無權限刪除此標籤")
        instance.delete()
        

class SavedWorkViewSet(viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication]
    serializer_class = SavedWorkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        member = Member.objects.get(id=self.request.user.id)
        return SavedWork.objects.filter(member=member)

    def perform_create(self, serializer):
        member = Member.objects.get(id=self.request.user.id)
        work_id = self.request.data.get('work')
        if not work_id:
            raise serializers.ValidationError({'work': 'work 為必填'})
        work = Work.objects.get(id=work_id)

        label_id = self.request.data.get('label', None)
        label = None
        if label_id is not None:
            try:
                label_id_int = int(label_id)
            except ValueError:
                raise serializers.ValidationError({'label': 'label 必須為數字'})

            if label_id_int == 0:
                # 找或建立 name 為空字串的 label
                label, created = WorkLabel.objects.get_or_create(member=member, name="bookmark")
            else:
                try:
                    label = WorkLabel.objects.get(id=label_id_int, member=member)
                except WorkLabel.DoesNotExist:
                    raise serializers.ValidationError({'label': '標籤不存在或不是你的'})
        # 不可重複收藏
        if SavedWork.objects.filter(member=member, work=work, label=label).exists():
            # raise serializers.ValidationError({'detail': '你已收藏過此作品'})
            return 'ok' #不打擾用戶算了
        serializer.save(member=member, work=work, label=label)