from django.db import models
from bs4 import BeautifulSoup
from member.models import Member
from django.utils.html import strip_tags

class Rss(models.Model):
    rss = models.URLField(unique=True, null=False, blank=False)
    sitename = models.CharField(max_length=256, default=None, null=True, blank=True)
    website = models.URLField(unique=True, default=None, null=True, blank=True)
    lang = models.CharField(max_length=32, default=None, null=True, blank=True)
    logo = models.ImageField(upload_to='sitelogo/', default=None, null=True, blank=True)
    createdate = models.DateTimeField(auto_now_add=True)
    lastupdate = models.DateTimeField(auto_now=True)
    blackcate = models.JSONField(null=True, blank=True)
    whitecate = models.JSONField(null=True, blank=True)
    lastfetch = models.DateTimeField(null=True, blank=True)
    magicword = models.CharField(max_length=100, default=None, null=True, blank=True)
    publish_frequency = models.PositiveIntegerField(
        default=1,
        null=False, 
        blank=False, 
        help_text="Average number of days between published articles (integer, minimum 1)."
    )
    scale = models.CharField(max_length=10, default=None, null=True, blank=True, help_text="indie/corp/group")
    total_irrelevant = models.PositiveIntegerField(default=0, null=False, blank=False)
    status = models.CharField(max_length=32, default="admin", choices=[("admin", "Admin"), ("user", "User")])
    recommender = models.ForeignKey('member.Member', on_delete=models.SET_NULL, null=True, blank=True, related_name='rss_recommender')
    # 只對 status='user'（會員推薦）有意義：null＝還沒審過，會算進 admin 首頁的待辦色塊。
    # 用時間戳而不是布林值，之後要查「什麼時候審的」不用再加欄位。
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.publish_frequency < 1:
            self.publish_frequency = 1
        super().save(*args, **kwargs)
    
class Work(models.Model):
    rss = models.ForeignKey(Rss, on_delete=models.CASCADE, related_name='works')
    url = models.URLField(max_length=512, unique=True, null=False, blank=False)
    title = models.CharField(max_length=512, default=None, null=True, blank=True)
    publishdate = models.DateTimeField(null=True, blank=True)
    lang = models.CharField(max_length=32, default=None, null=True, blank=True)
    irrelevant = models.PositiveSmallIntegerField(default=0, null=False, blank=False)
    flag = models.PositiveSmallIntegerField(default=0, null=False, blank=False)
    content = models.TextField(null=True, blank=True)
    image = models.URLField(max_length=512, null=True, blank=True)
    source = models.CharField(max_length=20, default=None, null=True, blank=True)
    content_length = models.PositiveIntegerField(default=0, null=False, blank=False)

    class Meta:
        indexes = [
            # FeedListView：filter(lang__in, irrelevant=0).order_by('-publishdate')，
            # 沒有索引時每次都全表掃描 + 排序整張表（含 content 的 102MB）
            models.Index(fields=["lang", "irrelevant", "-publishdate"], name="feed_work_lang_irr_pub_idx"),
        ]

    def save(self, *args, **kwargs):
        # 在保存前自動計算 content 中可見文字的字符數量
        if self.content:
            # 使用 BeautifulSoup 解析 HTML 並提取純文字
            soup = BeautifulSoup(self.content, 'html.parser')
            visible_text = soup.get_text(separator=' ', strip=True)
            self.content_length = len(visible_text)
        else:
            self.content_length = 0
        super(Work, self).save(*args, **kwargs)
        
    @property
    def preview(self):
        if not self.content:
            return ""
        return strip_tags(self.content)[:200]
        
class WorkTranslation(models.Model):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='translations')
    lang = models.CharField(max_length=10)  # 语言代码，如 'en', 'fr', 'es', 'de', 'zh'
    translated_title = models.CharField(max_length=256, null=True, blank=True)  # 翻译后的标题
    translated_content = models.TextField(null=True, blank=True)  # 翻译后的内容
    created_at = models.DateTimeField(auto_now_add=True)  # 翻译创建时间

class WorkLabel(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='labels')
    name = models.CharField(max_length=64, null=False, blank=False, default='bookmark')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('member', 'name')
        
class SavedWork(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='saved_works')
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='saved_by_members')
    label = models.ForeignKey(WorkLabel, null=True, blank=True, on_delete=models.SET_NULL, related_name='saved_works')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('member', 'work', 'label')