from django.contrib import admin
from .models import ContactInquiry, Conversation, ConversationParticipant, Message


@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject_preview', 'content_preview', 'created_at', 'is_read')
    list_filter = ('is_read', 'created_at')
    search_fields = ('name', 'email', 'subject', 'content')
    readonly_fields = ('created_at',)
    list_editable = ('is_read',)

    def subject_preview(self, obj):
        return obj.subject[:50] if obj.subject else '—'
    subject_preview.short_description = 'Subject'

    def content_preview(self, obj):
        return obj.content[:80] + '...' if len(obj.content) > 80 else obj.content
    content_preview.short_description = 'Content'


class ConversationParticipantInline(admin.TabularInline):
    model = ConversationParticipant
    extra = 0
    readonly_fields = ('joined_at', 'last_read_at')


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'is_group', 'participant_count', 'created_at', 'updated_at')
    list_filter = ('is_group', 'created_at')
    search_fields = ('title',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ConversationParticipantInline]

    def participant_count(self, obj):
        return obj.participants.count()
    participant_count.short_description = 'Participants'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_sender', 'conversation', 'content_preview', 'created_at', 'is_deleted')
    list_filter = ('is_deleted', 'created_at')
    search_fields = ('content', 'sender__id__username')
    readonly_fields = ('created_at',)

    def get_sender(self, obj):
        return obj.sender.id.username
    get_sender.short_description = 'Sender'

    def content_preview(self, obj):
        return obj.content[:80] + '...' if len(obj.content) > 80 else obj.content
    content_preview.short_description = 'Content'
