from django.contrib import admin
from .models import Msg

class MsgAdmin(admin.ModelAdmin):
    list_display = ('get_sender_username', 'guest_name', 'get_recipient_username', 'content_preview', 'timestamp', 'is_read')
    list_filter = ('is_read', 'timestamp')
    search_fields = ('content', 'guest_name', 'sender__id__username', 'recipient__id__username')
    readonly_fields = ('timestamp',)
    
    def content_preview(self, obj):
        """顯示 content 的前 50 個字符作為預覽"""
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    
    content_preview.short_description = 'Content Preview'
    
    def get_sender_username(self, obj):
        """顯示 sender 的 username"""
        if obj.sender and obj.sender.id:
            return obj.sender.id.username
        return "N/A"  # 如果 sender 為空或無關聯 User，返回 N/A
    
    get_sender_username.short_description = 'Sender'
    
    def get_recipient_username(self, obj):
        """顯示 recipient 的 username"""
        if obj.recipient and obj.recipient.id:
            return obj.recipient.id.username
        return "N/A"  # 如果 recipient 為空或無關聯 User，返回 N/A
    
    get_recipient_username.short_description = 'Recipient'

# 註冊 Msg 模型到 Django Admin
admin.site.register(Msg, MsgAdmin)