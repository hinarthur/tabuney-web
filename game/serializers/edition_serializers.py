"""
Edition 的 JSON 表示。

網站的搜尋頁（載入更多）與 App 的 /api/v1/ 端點共用同一份序列化規則，
避免兩邊各寫一份而慢慢漂移。
"""

from rest_framework import serializers

from game.selectors import (
    get_edition_flowchart,
    get_edition_skills,
    resolve_chat_status,
)
from translation.selectors import build_opening_message


class EditionCardSerializer(serializers.Serializer):
    """
    搜尋結果卡片。需要先經過 selectors.annotate_editions()，
    chat_status / has_* 欄位才會有值。
    """

    id = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    release_year = serializers.IntegerField()
    thumbnail = serializers.SerializerMethodField()
    min_players = serializers.IntegerField(source='game.min_players')
    max_players = serializers.IntegerField(source='game.max_players')
    min_playtime = serializers.IntegerField(source='game.min_playtime')
    max_playtime = serializers.IntegerField(source='game.max_playtime')
    age = serializers.IntegerField()
    color_vision_friendly = serializers.BooleanField(allow_null=True, required=False)
    chat_status = serializers.SerializerMethodField()
    has_flowchart = serializers.SerializerMethodField()
    has_skills = serializers.SerializerMethodField()
    has_published_script = serializers.SerializerMethodField()

    def get_id(self, obj):
        return str(obj.id)

    def get_name(self, obj):
        return obj.name or obj.game.canonical_name

    def get_thumbnail(self, obj):
        return obj.thumbnail.url if obj.thumbnail else None

    def get_chat_status(self, obj):
        return getattr(obj, 'search_chat_status', 'not_ready')

    def get_has_flowchart(self, obj):
        return getattr(obj, 'search_has_flowchart', False)

    def get_has_skills(self, obj):
        return getattr(obj, 'search_has_skills', False)

    def get_has_published_script(self, obj):
        return getattr(obj, 'search_has_script', False)


class EditionDetailSerializer(serializers.Serializer):
    """
    版本詳細資料。開場白依語言而異，語言由 context['lang'] 傳入
    （web 走 URL 前綴決定，API 走 ?lang=）。
    """

    id = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    slug = serializers.CharField()
    release_year = serializers.IntegerField()
    thumbnail = serializers.SerializerMethodField()
    min_players = serializers.IntegerField(source='game.min_players')
    max_players = serializers.IntegerField(source='game.max_players')
    min_playtime = serializers.IntegerField(source='game.min_playtime')
    max_playtime = serializers.IntegerField(source='game.max_playtime')
    age = serializers.IntegerField()
    color_vision_friendly = serializers.BooleanField(allow_null=True, required=False)
    summary = serializers.SerializerMethodField()
    chat_status = serializers.SerializerMethodField()
    opening_message = serializers.SerializerMethodField()
    flowchart = serializers.SerializerMethodField()
    has_skills = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()

    def get_id(self, obj):
        return str(obj.id)

    def get_name(self, obj):
        return obj.name or obj.game.canonical_name

    def get_thumbnail(self, obj):
        return obj.thumbnail.url if obj.thumbnail else None

    def get_summary(self, obj):
        return obj.summary or ""

    def _chat_status(self, obj):
        # 同一次序列化裡 chat_status 被三個欄位用到，快取避免重複查詢
        if not hasattr(self, '_chat_status_cache'):
            self._chat_status_cache = {}
        if obj.pk not in self._chat_status_cache:
            self._chat_status_cache[obj.pk] = resolve_chat_status(obj)
        return self._chat_status_cache[obj.pk]

    def get_chat_status(self, obj):
        return self._chat_status(obj)

    def get_opening_message(self, obj):
        lang = self.context.get('lang', 'en')
        name = obj.name or obj.game.canonical_name
        return build_opening_message(lang, name, self._chat_status(obj))

    def get_flowchart(self, obj):
        return get_edition_flowchart(obj)

    def get_has_skills(self, obj):
        return get_edition_skills(obj.game)[0]

    def get_skills(self, obj):
        return get_edition_skills(obj.game)[1]
