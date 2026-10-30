# serializers.py
from rest_framework import serializers
from .models import Work, Rss, SavedWork, WorkLabel
import re
from bs4 import BeautifulSoup, NavigableString

# class RssSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Rss
#         fields = ['id', 'sitename', 'logo']  # 根據你的需求選擇需要的欄位
class RssSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()  # 改用 SerializerMethodField
    
    def get_logo(self, obj):
        """動態生成完整的 logo URL"""
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
        return None
    
    class Meta:
        model = Rss
        fields = ['id', 'sitename', 'logo']

# ---- 這裡放fix_content_html function ----
def fix_content_html(raw):
    raw = (raw or '').strip()
    soup = BeautifulSoup(raw, "html.parser")
    new_contents = []
    for child in soup.contents:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                new_tag = soup.new_tag('p')
                new_tag.string = text
                new_contents.append(new_tag)
        else:
            new_contents.append(child)
    return ''.join(str(x) for x in new_contents)
        
class WorkSerializer(serializers.ModelSerializer):
    rss = RssSerializer()  # 這裡嵌套了 RssSerializer
    content = serializers.SerializerMethodField()  # 由方法動態生成
    
    class Meta:
        model = Work
        # fields = ['id', 'title', 'image', 'publishdate', 'content']
        fields = ['id', 'rss', 'url', 'title', 'publishdate', 'lang', 'irrelevant', 'flag', 'content', 'image', 'source']
        
    def get_content(self, obj):
        return fix_content_html(obj.content)
        
class SavedWorkSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedWork
        fields = ['id', 'member', 'work', 'label', 'saved_at']
        read_only_fields = ['id', 'member', 'label', 'saved_at']
        
class WorkLabelSerializer(serializers.ModelSerializer):
    saved_work_count = serializers.IntegerField(read_only=True)
    class Meta:
        model = WorkLabel
        fields = ['id', 'name', 'saved_work_count']