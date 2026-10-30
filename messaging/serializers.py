from rest_framework import serializers
from .models import ContactInquiry, Conversation, ConversationParticipant, Message


class ContactInquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactInquiry
        fields = ['id', 'name', 'email', 'subject', 'content', 'created_at']
        read_only_fields = ['id', 'created_at']


class MessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.IntegerField(source='sender.id.id', read_only=True)
    sender_username = serializers.CharField(source='sender.id.username', read_only=True)
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender_id', 'sender_username', 'content', 'created_at', 'is_read']
        read_only_fields = ['id', 'conversation', 'sender_id', 'sender_username', 'created_at', 'is_read']

    def get_is_read(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        try:
            participant = ConversationParticipant.objects.get(
                conversation=obj.conversation,
                member_id=request.user.id
            )
            if participant.last_read_at is None:
                return False
            return obj.created_at <= participant.last_read_at
        except ConversationParticipant.DoesNotExist:
            return False


class ConversationParticipantSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='member.id.username', read_only=True)
    avatar = serializers.URLField(source='member.avatar', read_only=True)

    class Meta:
        model = ConversationParticipant
        fields = ['member_id', 'username', 'avatar', 'joined_at', 'last_read_at']
        read_only_fields = ['member_id', 'username', 'avatar', 'joined_at', 'last_read_at']


class ConversationSerializer(serializers.ModelSerializer):
    participants = ConversationParticipantSerializer(many=True, read_only=True)
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'is_group', 'created_at', 'updated_at', 'participants', 'unread_count', 'last_message']
        read_only_fields = ['id', 'is_group', 'created_at', 'updated_at', 'participants', 'unread_count', 'last_message']

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        try:
            participant = obj.participants.get(member_id=request.user.id)
            return participant.unread_count()
        except ConversationParticipant.DoesNotExist:
            return 0

    def get_last_message(self, obj):
        msg = obj.messages.filter(is_deleted=False).last()
        if msg:
            return {
                'content': msg.content[:100],
                'sender_username': msg.sender.id.username,
                'created_at': msg.created_at,
            }
        return None
