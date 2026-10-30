# management/commands/fetch_rss.py
from django.core.management.base import BaseCommand
from feed.models import Rss
from django_q.tasks import async_task

#只用作手動fetch，定期fetch時不用此command
class Command(BaseCommand):
    help = 'Fetch latest articles from RSS feeds and save to database'

    
    def handle(self, *args, **kwargs):
        rss_feeds = Rss.objects.all()
        for rss_feed in rss_feeds:
            async_task('feed.tasks.fetch_one_rss', rss_feed.id)
            self.stdout.write(self.style.SUCCESS(f'Scheduled task for RSS feed: {rss_feed.id}'))
            
        # rss_feeds = Rss.objects.filter(id__in=[545]) #for 龐奇

        # today = datetime.now().date()
        # tomorrow = today + timedelta(days=1)
        # # 定义时区信息
        # tzinfos = {
        #     "EST": -5 * 3600,
        #     "EDT": -4 * 3600,
        #     # 添加其他时区映射
        # }
        
        # for rss_feed in rss_feeds:
        #     try:
        #         feed = feedparser.parse(rss_feed.rss)
        #         for entry in feed.entries:
        #             publish_date = None
                    
        #             # 嘗試從不同欄位解析日期
        #             date_fields = [
        #                 'dc_date',  # feedparser 會將 dc:date 轉換為 dc_date
        #                 'published',
        #                 'updated'
        #             ]
                    
        #             for field in date_fields:
        #                 try:
        #                     if hasattr(entry, field):
        #                         date_str = getattr(entry, field)
        #                         # publish_date = date_parser.parse(date_str).date()
        #                         publish_date = date_parser.parse(date_str, tzinfos=tzinfos).date()
        #                         break
        #                 except (AttributeError, ValueError):
        #                     continue
                    
        #             # 檢查是否為未來文章
        #             if publish_date and publish_date >= tomorrow:
        #                 continue

        #             # 檢查必要欄位
        #             if not hasattr(entry, 'link'):
        #                 self.stdout.write(self.style.WARNING("Entry has no link, skipping"))
        #                 continue
        #             decoded_url = unquote(entry.link)
                            
        #             # 檢查是否已存在
        #             if Work.objects.filter(url=decoded_url).exists():
        #                 # self.stdout.write(self.style.WARNING(f"Article already exists: {decoded_url}"))
        #                 continue

        #             # 內容處理
        #             content = ''
        #             # if 'content' in entry:
        #             if 'content' in entry and ("繼續閱讀" in entry.content[0].value or "Read more" in entry.content[0].value):
        #                 print('has read more')
        #                 # self.stdout.write(self.style.SUCCESS(f'oh content'))
        #                 content = self.fetch_full_content(decoded_url)
        #             elif 'fulltext' in entry:
        #                 print('fulltext')
        #                 # self.stdout.write(self.style.SUCCESS(f'oh fulltext'))
        #                 content = entry.fulltext
        #             elif 'content' in entry:
        #                 print('just content')
        #                 # self.stdout.write(self.style.SUCCESS(f'oh more'))
        #                 content = entry.content[0].value  # content 是一个列表，通常需要取第一个元素
        #             else:
        #                 print('summary/description')
        #                 # self.stdout.write(self.style.SUCCESS(f'oh short'))
        #                 content = entry.get('summary', entry.get('description', ''))
                                        
        #             # 提取圖片
        #             # 對於這種格式，可以從 content:encoded 中提取
        #             heroimage = None
        #             if hasattr(entry, 'content') and entry.content:
        #                 soup = BeautifulSoup(entry.content[0].get('value', ''), 'html.parser')
        #                 img_tag = soup.find('img')
        #                 if img_tag:
        #                     heroimage = img_tag.get('src')
                    
        #             # 如果沒有從 content 中找到，嘗試其他方法
        #             if not heroimage:
        #                 heroimage = self.extract_image(entry, feed)

        #             try:
        #                 Work.objects.create(
        #                     rss=rss_feed,
        #                     url=decoded_url,
        #                     title=entry.title,
        #                     publishdate=publish_date,
        #                     content=content,
        #                     image=heroimage,
        #                     lang=rss_feed.lang  # 使用 RSS 的 lang
        #                 )
        #                 self.stdout.write(self.style.SUCCESS(f'Successfully added article: {entry.title}'))
        #                 print(entry.title)
        #             except Exception as e:
        #                 self.stdout.write(self.style.ERROR(f"Error creating Work: {e}"))

        #     except Exception as e:
        #         self.stdout.write(self.style.ERROR(f'Error processing feed {rss_feed.sitename}: {e}'))
     