from django.conf import settings
from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone
from bs4 import BeautifulSoup
import feedparser
import requests
from django.http import HttpResponse
from member.models import Member
from feed.models import Work, Rss
from game.models import Rulebook, RulebookFlowchart, RulebookScript, Game, GameSuggestion, GameSuggestionStatus, FlowchartSuggestion
from stats.reports import (
    search_insights, all_page_visit_insights, language_click_insights,
    error_insights, server_insights, alert_ack_key,
)
from stats.models import ErrorAlertAck
from game.selectors import rulesbot_ready_rulebooks
from game.reports import flowchart_insights, rulesbot_insights, script_insights
from .prod_stats import fetch_prod_stats
from django.db.models import Count, Q
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from datetime import timedelta, datetime

class FeedPanel(admin.AdminSite):
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('', self.admin_view(self.index), name='index'),
        ]
        return custom_urls + urls
    
    def index(self, request):
        result = None
        error = None
        url = ''        
        
        if request.method == "POST" and 'site_url' in request.POST:
            url = request.POST['site_url'].strip()
            result_list = []
            error = ''
            try:
                # 1. 取得網站HTML
                resp = requests.get(url, timeout=10, headers={'User-Agent':'Mozilla/5.0'})
                soup = BeautifulSoup(resp.text, 'html.parser')
                # 2. 找出所有RSS連結
                feed_urls = []
                for link in soup.find_all('link', type=['application/rss+xml','application/atom+xml']):
                    feed_url = link.attrs.get('href')
                    if feed_url:
                        # 統一化為完整url
                        if feed_url.startswith('//'):
                            feed_url = 'https:' + feed_url
                        elif feed_url.startswith('/'):
                            feed_url = url.rstrip('/') + feed_url
                        elif not feed_url.startswith('http'):
                            feed_url = url.rstrip('/') + '/' + feed_url
                        # 避免重覆
                        if feed_url not in feed_urls:
                            feed_urls.append(feed_url)

                if not feed_urls:
                    error = "沒有在這個網站找到任何 RSS/Atom Feed"
                
                # 逐一處理所有RSS連結
                for feed_url in feed_urls:
                    # 3. 取網站標題
                    site_title = (soup.title and soup.title.string) or ''
                    # 4. 取logo
                    logo_url = None
                    d = feedparser.parse(feed_url)
                    if getattr(d.feed, "image", None) and hasattr(d.feed.image, "href"):
                        logo_url = d.feed.image.href
                    elif getattr(d.feed, "logo", None):
                        logo_url = d.feed.logo
                    elif getattr(d.feed, "author_detail", None):
                        author_img = None
                        if "avatar" in d.feed.author_detail:
                            author_img = d.feed.author_detail.avatar
                        elif "image" in d.feed.author_detail:
                            author_img = d.feed.author_detail.image
                        if author_img and author_img.startswith("http"):
                            logo_url = author_img
                    elif getattr(d.feed, "authors", None):
                        for author in d.feed.authors:
                            author_img = None
                            if "avatar" in author:
                                author_img = author["avatar"]
                            elif "image" in author:
                                author_img = author["image"]
                            if author_img and author_img.startswith("http"):
                                logo_url = author_img
                                break

                    # 5. 抓RSS資訊
                    language = d.feed.get('language', '')
                    if not site_title and 'title' in d.feed:
                        site_title = d.feed['title']
                    latest_entry_date = None
                    if getattr(d, "entries", None) and len(d.entries) > 0:
                        entry = d.entries[0]
                        if "published" in entry:
                            latest_entry_date = entry.published
                        elif "updated" in entry:
                            latest_entry_date = entry.updated

                    result = {
                        'rss_url': feed_url,
                        'site_title': site_title,
                        'logo_url': logo_url,
                        'language': language,
                        'site_url': url,
                        'latest_entry_date': latest_entry_date,
                    }
                    result_list.append(result)  ### 重點更改

            except Exception as e:
                error = "解析失敗：" + escape(str(e))
                
            context = {
                'result_list': result_list,   ### 重點更改
                'error': error,
                'site_url': url,
                'home_url': reverse('admin:index'),
                'custom_links': [
                    {
                        'title': 'Custom Admin Panel',
                        'url': reverse('feed_panel:index'),
                        'description': 'Go to Custom Admin Panel'
                    }
                ]
            }            
            response = render(request, 'admin/feedpanel.html', context)
            return response
        else:
            # 當不是 POST 請求或缺少 site_url 時，回傳預設頁面
            context = {
                'result_list': [],  # 預設為空列表
                'error': '',
                'site_url': '',
                'home_url': reverse('admin:index'),
                'custom_links': [
                    {
                        'title': 'Custom Admin Panel',
                        'url': reverse('feed_panel:index'),
                        'description': 'Go to Custom Admin Panel'
                    }
                ]
            }
            response = render(request, 'admin/feedpanel.html', context)
            if response is None:
                print("Response is None, fallback to HttpResponse")
                return HttpResponse("Feed Panel fallback response")
            return response

feed_panel = FeedPanel(name='feed_panel')

# 註冊一些基本模型
feed_panel.register(User)
feed_panel.register(Group)

class AdminStatsView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request, format=None):
        # 這台機器自己是不是正式站。前端靠它決定要不要顯示切換鈕：
        # 正式站上「本機」就是正式站資料庫，切換沒有意義。
        can_switch = settings.DJANGO_ENV != 'production'

        # 本機可以切成看正式站的數字（走 API 代理，不碰資料庫）。
        # DJANGO_ENV 守衛是必要的：正式站若也吃這個參數就會呼叫自己造成遞迴。
        if request.query_params.get('source') == 'prod' and can_switch:
            prod_data, error = fetch_prod_stats(
                force_refresh=request.query_params.get('refresh') == '1'
            )
            if error:
                return Response(
                    {
                        'stats_source': 'prod',
                        'stats_error': error,
                        'can_switch_source': can_switch,
                    },
                    status=502,
                )
            prod_data['stats_source'] = 'prod'
            # 一定要覆寫：prod_data 是正式站產生的，它自己的 can_switch_source 是
            # False。原樣回傳的話，本機切過去之後按鈕會消失、再也切不回來。
            prod_data['can_switch_source'] = can_switch
            return Response(prod_data)

        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        langs = ['en', 'de', 'fr', 'es', 'zh', 'ja']
        data = {}
        for lang in langs:
            qs = Work.objects.filter(
                publishdate__gte=thirty_days_ago,
                lang=lang
            )
            article_count = qs.count()
            content_lengths = qs.filter(content_length__gt=50).values_list('content_length', flat=True)
            avg_content_length = sum(content_lengths)/len(content_lengths) if content_lengths else 0
            
            rss_count = Rss.objects.filter(lang=lang).count()
            # print(rss_count)

            data[lang] = {
                'article_count_last_30_days': article_count,
                'avg_content_length_gt_50_last_30_days': avg_content_length,
                'rss_count': rss_count,
            }
        status = (
            Rss.objects
            .values('status')
            .annotate(count=Count('id'))
        )
        
        # # 人數分組
        # App 的使用行為統計（開app頻次／使用時長／瀏覽頁數／匿名訪客數）已移除：
        # 那些數字全部來自 member.UserActivity 的 open_app/close_app/page_view，
        # 對 member/subscriber 長期都是 0，且「訪客」數的是 App 的匿名 session_id，
        # 與網站訪客無關。SearchLog.source 仍照記，只是不在首頁顯示。
        data['total_free'] = Member.objects.filter(tier_new__code='member').count()
        data['total_basic'] = Member.objects.filter(tier_new__code='subscriber').count()
        data['page_visit_insights'] = all_page_visit_insights()

        # # 語言數據：只看 member/subscriber 兩種 tier 的介面語言，feed 相關的語言
        # 數據（feedfilter_lang / feed_detail_views / source_clicks）不再需要。
        langs = ['de', 'en', 'es', 'fr', 'ja', 'zh']
        data['tribe_counts'] = {
            l: Member.objects.filter(
                tier_new__code__in=['member', 'subscriber'],
                tribe__language=l,
            ).count()
            for l in langs
        }

        # 上面的 tribe_counts 是「存下來的偏好」快照（只有會員、沒有時間軸）；
        # 這個是實際的切換行為，含匿名訪客
        data['language_click_insights'] = language_click_insights()

        # 會員送出的兩種建議各狀態數量（狀態選項共用 GameSuggestionStatus）：
        # - game_suggestion_counts：搜尋頁的「推薦新增桌遊」
        # - flowchart_suggestion_counts：流程圖分頁的「改善建議」
        # 外加 RSS 推薦（會員自行加入，status='user'）數量。
        data['game_suggestion_counts'] = {
            choice_value: GameSuggestion.objects.filter(status=choice_value).count()
            for choice_value, _ in GameSuggestionStatus.choices
        }
        data['flowchart_suggestion_counts'] = {
            choice_value: FlowchartSuggestion.objects.filter(status=choice_value).count()
            for choice_value, _ in GameSuggestionStatus.choices
        }
        data['rss_user_suggestion_count'] = Rss.objects.filter(status='user').count()
        # 待辦色塊用的是這個：還沒在 Rss admin 按過「標記已審」的會員推薦
        data['rss_user_pending_count'] = Rss.objects.filter(
            status='user', reviewed_at__isnull=True
        ).count()

        # Rulebook 統計
        # 2026-08 起 rulesbot 的就緒判準是 whole_context 非空（見 selectors），
        # 不再看 status：status 殘留 pending/indexed 的舊值，數它會和實際不符。
        # 鍵名沿用 rulebook_indexed_count 是因為正式站的 API 代理回傳同一組鍵。
        _ready = rulesbot_ready_rulebooks()
        data['rulebook_indexed_count'] = _ready.count()
        # 待處理 = 有 PDF 但還沒填 whole_context（沒有檔案的 scraper 殘留不算）
        data['rulebook_pending_count'] = (
            Rulebook.objects.filter(whole_context="").exclude(file="").count()
        )
        # Source URL 失效：總數，以及「上次成功 sync 之後才變成 broken」的新發現數
        # （狀態變動時 check_rulebook_source_urls 會動 updated_at，見該指令）。
        # 新發現 > 0 代表有變動還沒同步到正式站，該跑 sync 了。
        from game.sync_models import GameSyncLog
        _broken = Rulebook.objects.filter(source_url_status='broken').exclude(source_url='')
        _last_sync = (
            GameSyncLog.objects.filter(status=GameSyncLog.Status.SUCCESS)
            .order_by('-created_at').values_list('created_at', flat=True).first()
        )
        data['rulebook_source_broken_total'] = _broken.count()
        data['rulebook_source_broken_new'] = (
            _broken.filter(updated_at__gt=_last_sync).count() if _last_sync else _broken.count()
        )
        # Flowchart 一格拆成「入門圖 | 變體圖」兩個數字（initial=True / False）。
        # 母體是「已公開」（reviewer 核准且未下架）：公開頁、sitemap 實際看得到的才算。
        # 翻譯狀態不納入——沒翻完的圖仍然已經上線（以原語言顯示）。
        _fc_translated = RulebookFlowchart.objects.published()
        data['rulebook_flowchart_translated_count'] = _fc_translated.count()
        data['rulebook_flowchart_initial_count'] = _fc_translated.filter(initial=True).count()
        data['rulebook_flowchart_variant_count'] = _fc_translated.filter(initial=False).count()
        # 待審＝最新一筆審核紀錄是「送審」，且送審的就是目前這一版（送審後沒再改過）
        from django.db.models import F, OuterRef, Subquery
        from game.models import FlowchartReview
        _latest_review = FlowchartReview.objects.filter(flowchart=OuterRef('pk')).order_by('-created_at')
        data['rulebook_flowchart_pending_review_count'] = (
            RulebookFlowchart.objects.annotate(
                _la=Subquery(_latest_review.values('action')[:1]),
                _lh=Subquery(_latest_review.values('content_hash')[:1]),
            ).filter(_la=FlowchartReview.Action.SUBMITTED, _lh=F('content_hash')).count()
        )
        # ── 待辦色塊：製作流程的各關卡積壓 ──
        # 待搜／待寫入：Edition import queue 的兩個「等人動手」狀態
        from game.models import EditionImportQueue
        _Q = EditionImportQueue.Status
        data['edition_import_searching_count'] = EditionImportQueue.objects.filter(status=_Q.SEARCHING).count()
        data['edition_import_review_count'] = EditionImportQueue.objects.filter(status=_Q.REVIEW).count()
        # 待生圖：whole_context 已備妥（rulesbot 可用）、卻還沒有任何入門圖的 rulebook。
        # 不是兩個總數相減：入門圖只要「生成過」就算，不看有沒有發布（沒發布的歸待檢圖），
        # 否則剛生成、還在等審的圖會同時掛在待生圖和待檢圖兩邊。
        data['rulebook_flowchart_to_generate_count'] = (
            rulesbot_ready_rulebooks().exclude(flowcharts__initial=True).count()
        )
        # 待檢圖：審核狀態不是「已發布」（state=live：公開版與草稿相同）。
        # 判準與 FlowchartReviewStatusFilter 的 live 一致：沒公開、或公開了但草稿又改過，都算。
        data['rulebook_flowchart_unpublished_count'] = (
            RulebookFlowchart.objects
            .exclude(publication__is_live=True, publication__content_hash=F('content_hash'))
            .count()
        )
        # 講稿數的是「已對前台公開」而不是「已生成」：生成完但沒勾 is_published 的
        # 還沒有人看得到，比照 flowchart 只數翻譯完成的那格。
        # 同一份講稿的各語言版本（rulebook + ruleset 相同、language 不同）算一筆，
        # 這裡看的是「有幾份講稿上線」，不是產出了幾個語言檔。
        data['rulebook_script_published_count'] = (
            RulebookScript.objects
            .filter(is_published=True)
            .values('rulebook', 'ruleset')
            .distinct()
            .count()
        )
        data['game_platvm_non_zero_count'] = Game.objects.filter(
            Q(adaptability__gt=0) | Q(collaboration__gt=0) | Q(communication__gt=0) |
            Q(creativity__gt=0) | Q(critical_thinking__gt=0) | Q(problem_solving__gt=0)
        ).count()

        # 各功能的報表：聚合邏輯都放在各 app 的 reports.py，這個 view 已經夠肥了不要再塞
        data['search_insights'] = search_insights()
        data['rulesbot_insights'] = rulesbot_insights()
        data['flowchart_insights'] = flowchart_insights()
        data['script_insights'] = script_insights()
        data['error_insights'] = error_insights()
        data['server_insights'] = server_insights()

        # context = locals()
        # return render(request, 'admin/stats_dashboard.html', context)

        data['status'] = status
        data['stats_source'] = 'local'
        data['can_switch_source'] = can_switch
        # print('============= all data ===================')
        # print(data)
        return Response(data)



class ErrorAlertAckView(APIView):
    """
    admin 首頁錯誤警示的「已處理」按鈕。

    key 在這裡重算而不是吃前端傳來的：前端只送 kind/path/referer，算法只存在
    stats.reports.alert_ack_key 一處，兩邊不會各算各的。
    重複按同一條只會更新 acked_at，不會生第二列。
    """
    permission_classes = [IsAdminUser]

    def post(self, request, format=None):
        kind = request.data.get('kind', '')
        path = request.data.get('path', '')
        referer = request.data.get('referer', '')
        if not kind or not path:
            return Response({'error': 'kind 與 path 必填'}, status=400)
        ErrorAlertAck.objects.update_or_create(
            key=alert_ack_key(kind, path, referer),
            defaults={
                'kind': kind,
                'path': path[:500],
                'referer': referer[:500],
                'acked_at': timezone.now(),
                'acked_by': request.user,
            },
        )
        return Response({'ok': True})
