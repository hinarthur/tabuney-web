from django.contrib import admin
from django.conf import settings
from .models import Rss, Work, SavedWork, WorkLabel
from .tasks import fetch_one_rss
from django.contrib import messages
from django.utils import timezone
from django.urls import path
from django.shortcuts import render, redirect
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from urllib.parse import unquote
from googleapiclient.discovery import build
 
## 手動fetch 指定rss源
@admin.action(description="馬上抓取所選 RSS")
def fetch_selected_rss(modeladmin, request, queryset):
    for rss in queryset:
        try:
            fetch_one_rss(rss.id)  # 同步呼叫
            messages.success(request, f"成功抓取: {rss.rss}")
        except Exception as e:
            messages.error(request, f"抓取失敗: {rss.rss}，錯誤：{e}")


@admin.action(description="標記已審（從首頁待辦移除）")
def mark_rss_reviewed(modeladmin, request, queryset):
    updated = queryset.filter(reviewed_at__isnull=True).update(reviewed_at=timezone.now())
    messages.success(request, f"已標記 {updated} 筆")


class RssReviewFilter(admin.SimpleListFilter):
    title = '審核'
    parameter_name = 'review'

    def lookups(self, request, model_admin):
        return [('pending', '會員推薦・未審'), ('done', '已審')]

    def queryset(self, request, queryset):
        if self.value() == 'pending':
            return queryset.filter(status='user', reviewed_at__isnull=True)
        if self.value() == 'done':
            return queryset.filter(reviewed_at__isnull=False)


@admin.register(Rss)
class RssAdmin(admin.ModelAdmin):
    list_display = ('sitename', 'lang', 'publish_frequency','rss','lastfetch', 'logo', 'status', 'createdate', 'reviewed_at')
    list_filter = (RssReviewFilter, 'lang', 'status')
    search_fields = ('sitename',)
    # list_editable = ('lang',)
    actions = [fetch_selected_rss, mark_rss_reviewed]
    ordering = ('-createdate',)
   

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('search-rss/', self.admin_site.admin_view(self.search_rss), name='search_rss'),
            path('add-rss/', self.admin_site.admin_view(self.add_rss), name='add_rss'),  # 不再使用路徑參數
        ]
        return custom_urls + urls

    def search_rss(self, request):
        if request.method == 'POST':
            api_key = settings.GOOGLE_CSE_API_KEY
            cx = settings.GOOGLE_CSE_CX
            if not api_key or not cx:
                messages.error(request, ".env 缺少 GOOGLE_CSE_API_KEY / GOOGLE_CSE_CX")
                return render(request, 'admin/search_rss.html', {'site': self.admin_site})

            try:
                service = build('customsearch', 'v1', developerKey=api_key)
                keywords = {
                    # 'en': 'board game blog RSS -news -corporate',
                    'zh': '桌遊 blog -新聞 -商業 -facebook',
                    # 'ja': 'ボードゲーム ブログ blog RSS -ニュース -企業',
                }
                # 對應語言代碼的映射
                language_restrictions = {
                    'en': 'lang_en',  # 英文
                    'zh': 'lang_zh-TW',  #  (或使用 'lang_zh-CN')
                    'ja': 'lang_ja',  # 日文
                }
                unwanted_domains = [
                    'google.com', 'facebook.com', 'instagram.com', 'rss.com', 'feedburner.com', 'podbean.com']
                
                results = []
                raw_results_count = {}  # 記錄每個關鍵字的原始結果數量
                existing_rss = set(Rss.objects.values_list('rss', flat=True))
                
                for lang, keyword in keywords.items():
                    res = service.cse().list(
                        q=keyword,
                        cx=cx,
                        dateRestrict='d30',  # 限制最近 30 天
                        num=10,  # 每種語言返回最多 10 個結果
                        lr=language_restrictions[lang]  # 設置語言限制
                    ).execute()
                    
                    items = res.get('items', [])
                    raw_results_count[lang] = len(items)  # 記錄原始結果數量
                    print(f"Raw results for {lang} ({keyword}): {len(items)} items")  # 控制台日誌
                    
                    for item in res.get('items', []):
                        href = item.get('link', '')
                        # if 'feed' in href.lower() or 'rss' in href.lower():
                        if href not in existing_rss:
                            parsed = urlparse(href)
                            sitename = parsed.netloc or 'Unknown'
                            if any(domain in sitename.lower() for domain in unwanted_domains):
                                continue
                            website = f"{parsed.scheme}://{parsed.netloc}"
                            results.append({
                                'sitename': sitename,
                                'rss_url': href,
                                'website': website,
                                'lang': lang,
                                'logo': None,
                            })
                
                context = {
                    'results': results,
                    'site': self.admin_site,
                }
                return render(request, 'admin/search_rss.html', context)
            except Exception as e:
                messages.error(request, f"Error fetching search results: {str(e)}")
                return render(request, 'admin/search_rss.html', {'site': self.admin_site})
        return render(request, 'admin/search_rss.html', {'site': self.admin_site})

    def add_rss(self, request):
        if request.method == 'GET':
            rss_url = request.GET.get('rss_url', '')
            sitename = request.GET.get('sitename', '')
            website = request.GET.get('website', '')
            lang = request.GET.get('lang', '')
            try:
                Rss.objects.create(
                    rss=rss_url,
                    sitename=sitename,
                    website=website,
                    lang=lang,
                    publish_frequency=1,  # 預設值
                )
                messages.success(request, f"RSS source {rss_url} has been added successfully.")
            except Exception as e:
                messages.error(request, f"Failed to add RSS source: {str(e)}")
        return redirect('admin:search_rss')

@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'source', 'lang', 'content_length', 'publishdate', 'image')
    list_filter = ('lang', 'publishdate')
    search_fields = ('title', 'content')
    # list_editable = ('lang',)
    
    # 可選：自定義排序
    ordering = ('-publishdate',)
        
    # 可選：分組顯示欄位
    fieldsets = (
        ('基本信息', {
            'fields': ('title', 'rss', 'url', 'source')
        }),
        ('內容詳情', {
            'fields': ('content', 'image', 'publishdate', 'irrelevant')
        }),
    )
   
@admin.register(SavedWork)
class SavedWorkAdmin(admin.ModelAdmin):
    list_display = ('member', 'work', 'label', 'saved_at',)
    
@admin.register(WorkLabel)
class WorkLabelAdmin(admin.ModelAdmin):
    list_display = ('member', 'name', 'created_at',)
