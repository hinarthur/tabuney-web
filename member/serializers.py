# member/serializers.py
from rest_framework import serializers
from .models import Member, UserActivity, Tier


class TierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tier
        fields = ['code', 'name']

class MemberSerializer(serializers.ModelSerializer):
    tribe_name = serializers.SerializerMethodField()
    email = serializers.CharField(source='id.email', read_only=True)
    first_name = serializers.CharField(source='id.first_name', read_only=True)
    
    # 新增：完整 tier 資訊
    # tier_info = TierSerializer(source='tier', read_only=True)    
    tier_info = TierSerializer(source='tier_new', read_only=True)
    
    tier = serializers.SerializerMethodField()
    class Meta:
        model = Member
        fields = ['id', 'avatar', 'email', 'first_name', 'tribe', 'tribe_name', 'feedlist_style', 'feedlist_lang', 'tier', 'tier_info']
        depth = 1  # 这将自动序列化外键关系

    def get_tribe_name(self, obj):
        # 如果 tribe 存在，返回 tribe 的名称，否则返回 None
        return obj.tribe.name if obj.tribe else None

    def get_tier(self, obj):
        return obj.tier_code_for_api
    
class UserActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivity
        fields = ['event_type', 'page', 'lang', 'meta', 'session_id', 'created_at']
        read_only_fields = ['created_at']