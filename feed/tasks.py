# from django_q.tasks import schedule, Schedule
from django_q.tasks import schedule as q_schedule
from django_q.models import Task, Schedule as QSchedule
import feedparser
from django.utils import timezone
from dateutil import parser as date_parser
from urllib.parse import unquote
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests
from feed.models import Work, Rss
from statistics import mean
from urllib.parse import urljoin

def extract_image(entry, feed):
    # 嘗試多種方法提取圖片
    image_urls = []
    base_url = entry.get('link', '').split('/')[0] + '//' + entry.get('link', '').split('/')[2] if entry.get('link') else ''
    # abnormal_domain = "belloflostsouls.net"


    # # 方法1：檢查 entry.content 中的第一張圖片
    # if hasattr(entry, 'content') and entry.content:
    #     soup = BeautifulSoup(entry.content[0].get('value', ''), 'html.parser')
    #     img_tag = soup.find('img')
    #     if img_tag:
    #         src = img_tag.get('src')
    #         if src:
    #             image_urls.append(src)
                
    # # 方法2：直接從 entry 中提取
    # if hasattr(entry, 'media_content') and entry.media_content:
    #     # image_urls.extend([media.get('url') for media in entry.media_content if media.get('url')])
    #     for media in entry.media_content:
    #         url = media.get('url')
    #         if url:
    #             # 只有當 URL 包含特定域名時才執行 clean_url
    #             if abnormal_domain in url:
    #                 url = clean_url(url)
    #             image_urls.append(url)
    
    # if hasattr(entry, 'links'):
    #     image_urls.extend([link.get('href') for link in entry.links if link.get('type', '').startswith('image')])
    
    # # 方法3：從 entry summary 中提取
    # if entry.get('summary'):
    #     soup = BeautifulSoup(entry.summary, 'html.parser')
    #     img_tags = soup.find_all('img')
    #     # image_urls.extend([img.get('src') for img in img_tags if img.get('src')])
    #     for img in img_tags:
    #         src = img.get('src')
    #         if src:
    #             # 如果是相對路徑，拼接成絕對路徑
    #             if not src.startswith('http'):
    #                 src = urljoin(base_url, src)
    #             image_urls.append(src)
    
    
    # 方法1：直接從 entry 的 media_content 中提取（次高優先級，因為專為媒體設計）
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            url = media.get('url')
            if url:
                # if abnormal_domain in url:
                #     url = clean_url(url)
                image_urls.append(url)
        if image_urls:
            return image_urls[0]  # 找到圖片後直接返回，避免不必要的處理

    # 方法2：檢查 entry.content 中的第一張圖片
    if hasattr(entry, 'content') and entry.content:
        soup = BeautifulSoup(entry.content[0].get('value', ''), 'html.parser')
        img_tag = soup.find('img')
        if img_tag:
            src = img_tag.get('src')
            if src:
                image_urls.append(src)
        if image_urls:
            return image_urls[0]

    # 方法3：從 entry.links 中提取 image 類型的連結
    if hasattr(entry, 'links'):
        link_images = [link.get('href') for link in entry.links if link.get('type', '').startswith('image')]
        image_urls.extend(link_images)
        if image_urls:
            return image_urls[0]
    
    # 方法4：從 entry summary 中提取
    if entry.get('summary'):
        soup = BeautifulSoup(entry.summary, 'html.parser')
        img_tags = soup.find_all('img')
        for img in img_tags:
            src = img.get('src')
            if src:
                # 如果是相對路徑，拼接成絕對路徑
                if not src.startswith('http'):
                    src = urljoin(base_url, src)
                image_urls.append(src)
        if image_urls:
            return image_urls[0]
    
    # # 方法4：嘗試從文章頁面提取
    # if not image_urls and entry.get('link'):
    #     try:
    #         response = requests.get(entry.link, timeout=5)
    #         soup = BeautifulSoup(response.text, 'html.parser')
            
    #         # 嘗試找主要圖片
    #         og_image = soup.find('meta', property='og:image')
    #         if og_image:
    #             image_urls.append(og_image.get('content'))
            
    #         # 如果還是沒有，找頁面中的第一張圖
    #         if not image_urls:
    #             img_tags = soup.find_all('img')
    #             # image_urls.extend([img.get('src') for img in img_tags if img.get('src')])
    #             for img in img_tags:
    #                 src = img.get('src')
    #                 if src:
    #                     if not src.startswith('http'):
    #                         src = urljoin(base_url, src)
    #                     image_urls.append(src)
        
    #     except Exception as e:
    #         print("Error extracting image from {entry.link}:" ,{e})
    
    # 過濾和驗證圖片 URL
    valid_image_urls = [
        url for url in image_urls 
        if url and (url.startswith('http') or url.startswith('https'))
    ]
    
    return valid_image_urls[0] if valid_image_urls else None      
           
def fetch_full_content(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # 根据网页结构提取文章内容
        content_div = soup.find('div', class_='article-content')
        if content_div:
            return str(content_div), 'article-content'
        content_div = soup.find('div', class_='entry-content')
        if content_div:
            return str(content_div), 'entry-content'
        article_tag = soup.find('article')
        if article_tag:
            return str(article_tag), 'article'
        # else:
        return "Content not found", 'not-found'
    except requests.RequestException as e:
        print(f"Error fetching full content: {e}")
        return "Error fetching full content"
        
def get_tzinfo(tzname, tzoffset=None):
    # 定义已知时区
    known_tzinfos = {
        "EST": -5 * 3600,
        "EDT": -4 * 3600,
        "PST": -8 * 3600,
        "PDT": -7 * 3600,
        # 添加其他已知时区
    }
    return known_tzinfos.get(tzname)


def update_publish_frequency(rss_instance):
    # 從 Work 模型中獲取與此 RSS 相關的最近10篇文章，按發布日期降序排列
    articles = Work.objects.filter(rss=rss_instance).order_by('-publishdate')[:10]
    if len(articles) < 2:
        rss_instance.publish_frequency = 1  # 不夠資料計算頻率，設為1
        rss_instance.save()
        return
    
    # 計算相鄰文章的時間差（天數）
    time_diffs = []
    for i in range(len(articles) - 1):
        if articles[i].publishdate and articles[i+1].publishdate:
            diff = (articles[i].publishdate - articles[i+1].publishdate).days
            if diff > 0:  # 確保時間差是合理的正數
                time_diffs.append(diff)
    
    # 如果有有效的時間差，計算平均天數並取整，確保至少為1
    if time_diffs:
        avg_days = max(1, round(mean(time_diffs)))
        rss_instance.publish_frequency = avg_days
    else:
        rss_instance.publish_frequency = 1  # 無法計算時設為1
    rss_instance.save()
    
def fetch_one_rss(rss_id):
    # print('fetching rss id: ', rss_id)
    # rss_feed = Rss.objects.get(id=rss_id)    
    try:
        rss_feed = Rss.objects.get(id=rss_id)
    except Rss.DoesNotExist:
        print(f"RSS ID {rss_id} does not exist. Cleaning up schedule.")

        # 嘗試找出並刪除相關的排程任務
        task_name = f"Fetch RSS {rss_id}"
        deleted, _ = QSchedule.objects.filter(name=task_name).delete()
        print(f"Deleted {deleted} schedule(s) named '{task_name}'")

        return  # 提早結束函數
    
    feed = feedparser.parse(rss_feed.rss)
    
    now = timezone.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    # 更新 lastfetch 欄位
    rss_feed.lastfetch = timezone.now()
    rss_feed.save()
    
    for entry in feed.entries:
        publish_date = None
        
        # 嘗試從不同欄位解析日期
        date_fields = [
            'dc_date',  # feedparser 會將 dc:date 轉換為 dc_date
            'published',
            'updated'
        ]
        
        for field in date_fields:
            try:
                if hasattr(entry, field):
                    date_str = getattr(entry, field)
                    publish_date = date_parser.parse(date_str, tzinfos=get_tzinfo)
                    # 检查并处理时区信息
                    if timezone.is_naive(publish_date):
                        publish_date = timezone.make_aware(publish_date, timezone.get_current_timezone())
                    # 將 publish_date 轉換為 UTC
                    publish_date = publish_date.astimezone(timezone.utc)
                    break
            except (AttributeError, ValueError):
                continue
        
        # 檢查是否為未來文章
        # if publish_date and publish_date >= tomorrow:
        if publish_date and publish_date >= tomorrow.astimezone(timezone.utc):
            continue

        # 檢查必要欄位
        if not hasattr(entry, 'link'):
            print("Entry has no link, skipping")
            continue
        decoded_url = unquote(entry.link)
                
        # 檢查是否已存在
        if Work.objects.filter(url=decoded_url).exists():
            continue

        # 內容處理
        content = ''
        source = None  # 初始化 source
        
         
        # # 檢查 category 是否在 blackcate 中
        # if hasattr(entry, 'category') and rss_feed.blackcate:
        #     entry_categories = entry.category if isinstance(entry.category, list) else [entry.category]
        #     black_cate_list = rss_feed.blackcate if isinstance(rss_feed.blackcate, list) else [rss_feed.blackcate]
        #     if any(cat in black_cate_list for cat in entry_categories):
        #         print(f"Skipping entry due to blacklisted category: {entry.title}")
        #         continue
        
        # 檢查 category 是否符合條件
        if hasattr(entry, 'category'):
            entry_categories = entry.category if isinstance(entry.category, list) else [entry.category]
            
            # 如果 whitecate 存在且不為空，則只 fetch 符合 whitecate 的 entry
            if rss_feed.whitecate:
                white_cate_list = rss_feed.whitecate if isinstance(rss_feed.whitecate, list) else [rss_feed.whitecate]
                if not any(cat in white_cate_list for cat in entry_categories):
                    print(f"Skipping entry due to not matching whitelist category: {entry.title}")
                    continue
                    
            # 如果 whitecate 為空，則檢查 blackcate，排除在 blackcate 中的 entry
            elif rss_feed.blackcate:
                black_cate_list = rss_feed.blackcate if isinstance(rss_feed.blackcate, list) else [rss_feed.blackcate]
                if any(cat in black_cate_list for cat in entry_categories):
                    print(f"Skipping entry due to blacklisted category: {entry.title}")
                    continue
        
        # 檢查 magicword 是否在 title 中
        if rss_feed.magicword and rss_feed.magicword not in entry.title:
            print(f"Skipping entry due to missing magic word: {entry.title}")
            continue
        
        # if 'content' in entry and any(keyword in entry.content[0].value for keyword in ["繼續閱讀", "Read more", "[&#8230;]", "Continue reading"]):
        #     # print('has read more')
        #     # self.stdout.write(self.style.SUCCESS(f'oh content'))
        #     # content = self.fetch_full_content(decoded_url)
        #     content = fetch_full_content(decoded_url)
        
        #fetch_full for all summary and description
        # if 'content' in entry and any(keyword in entry.content[0].value for keyword in ["繼續閱讀", "Read more", "[…]", "Continue reading"]):
        #     content, source = fetch_full_content(decoded_url)
            # source = 'fetch'
        # elif 'description' in entry and any(keyword in entry.description for keyword in ["繼續閱讀", "Read more", "[…]", "Continue reading"]):
        #     content = fetch_full_content(decoded_url)
        #     source = 'fetch'
        if hasattr(entry, 'encoded'):
            content = entry.encoded
            source = 'encoded'
        elif 'fulltext' in entry:
            content = entry.fulltext
            source = 'fulltext'
        elif 'content' in entry:
            content = entry.content[0].value  # content 是一个列表，通常需要取第一个元素
            source = 'content'
        elif 'summary' in entry or 'description' in entry:
            content = entry.get('summary', entry.get('description', ''))
            source = 'summary' if 'summary' in entry else 'description'
        else:
            content = "<content not found>"
            source = "empty"
                            
        # 提取圖片
        # 對於這種格式，可以從 content:encoded 中提取
        heroimage = None
        # if hasattr(entry, 'content') and entry.content:
        #     soup = BeautifulSoup(entry.content[0].get('value', ''), 'html.parser')
        #     img_tag = soup.find('img')
        #     if img_tag:
        #         heroimage = img_tag.get('src')
        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            for thumbnail in entry.media_thumbnail:
                url = thumbnail.get('url')
                if url:
                    heroimage = url
                    break  # 找到第一張有效圖片就停止
        
        # 如果沒有從 content 中找到，嘗試其他方法
        if not heroimage:
            # heroimage = self.extract_image(entry, feed)
            heroimage = extract_image(entry, feed)
    
        abnormal_domain = "belloflostsouls.net"
        if heroimage and abnormal_domain in heroimage:            
            heroimage = clean_url(heroimage)

        try:
            Work.objects.create(
                rss=rss_feed,
                url=decoded_url,
                title=entry.title,
                publishdate=publish_date,
                content=content,
                image=heroimage,
                lang=rss_feed.lang,  # 使用 RSS 的 lang
                source=source,
            )
            # self.stdout.write(self.style.SUCCESS(f'Successfully added article: {entry.title}'))
            # print(entry.title)
        except Exception as e:
            # self.stdout.write(self.style.ERROR(f"Error creating Work: {e}"))
            print("Error creating Work: ", {e})

    # 在處理完所有文章後，更新 publish_frequency
    update_publish_frequency(rss_feed)
    
def clean_url(url): #應對"Bell of Lost Souls" RSS的圖址錯誤
    if not url:
        return url
    base_domain = "https://www.belloflostsouls.net"
    error_prefix = base_domain + "/www.belloflostsouls.net/"
    if url.startswith(error_prefix):
        # 取出 error_prefix 之後的路徑
        url = base_domain + url[len(error_prefix) - 1:]  # -1因為還要保留/，或直接拼回"/wp-c..."
    return url
