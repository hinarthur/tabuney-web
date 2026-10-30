from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings

from member.models import Member
from .models import ContactInquiry, Conversation, ConversationParticipant, Message
from .serializers import (
    ContactInquirySerializer,
    ConversationSerializer,
    MessageSerializer,
)


@method_decorator(csrf_exempt, name='dispatch')
class ContactInquiryView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ContactInquirySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        inquiry = serializer.save()

        try:
            send_mail(
                subject=f'[TableJourney] New inquiry from {inquiry.name}',
                message=(
                    f'Name: {inquiry.name}\n'
                    f'Email: {inquiry.email}\n'
                    f'Subject: {inquiry.subject or "(none)"}\n\n'
                    f'{inquiry.content}'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.CONTACT_NOTIFY_EMAIL],
                fail_silently=True,
            )
        except Exception:
            pass

        return Response({'message': 'Your message has been received.'}, status=status.HTTP_201_CREATED)


class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        participant_qs = ConversationParticipant.objects.filter(
            member_id=request.user.id
        ).select_related('conversation').values_list('conversation_id', flat=True)
        conversations = Conversation.objects.filter(id__in=participant_qs).prefetch_related('participants__member__id')
        serializer = ConversationSerializer(conversations, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        participant_ids = request.data.get('participant_ids', [])
        title = request.data.get('title', '')

        if not participant_ids:
            return Response({'error': 'participant_ids is required.'}, status=status.HTTP_400_BAD_REQUEST)

        all_member_ids = list(set([request.user.id] + [int(pid) for pid in participant_ids]))
        members = Member.objects.filter(id__in=all_member_ids)
        if members.count() != len(all_member_ids):
            return Response({'error': 'One or more members not found.'}, status=status.HTTP_404_NOT_FOUND)

        is_group = len(all_member_ids) > 2

        with transaction.atomic():
            # For 1-on-1: reuse existing conversation if one exists
            if not is_group and len(all_member_ids) == 2:
                other_id = [pid for pid in all_member_ids if pid != request.user.id][0]
                existing = ConversationParticipant.objects.filter(
                    member_id=request.user.id,
                    conversation__participants__member_id=other_id,
                    conversation__is_group=False,
                ).select_related('conversation').first()
                if existing:
                    serializer = ConversationSerializer(existing.conversation, context={'request': request})
                    return Response(serializer.data, status=status.HTTP_200_OK)

            conversation = Conversation.objects.create(
                title=title or None,
                is_group=is_group,
            )
            ConversationParticipant.objects.bulk_create([
                ConversationParticipant(conversation=conversation, member_id=mid)
                for mid in all_member_ids
            ])

        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConversationMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_participant(self, conversation_id, user_id):
        try:
            return ConversationParticipant.objects.get(
                conversation_id=conversation_id,
                member_id=user_id,
            )
        except ConversationParticipant.DoesNotExist:
            return None

    def get(self, request, conversation_id):
        participant = self._get_participant(conversation_id, request.user.id)
        if not participant:
            return Response({'error': 'Not a participant.'}, status=status.HTTP_403_FORBIDDEN)

        messages = Message.objects.filter(
            conversation_id=conversation_id,
            is_deleted=False,
        ).select_related('sender__id')
        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request, conversation_id):
        participant = self._get_participant(conversation_id, request.user.id)
        if not participant:
            return Response({'error': 'Not a participant.'}, status=status.HTTP_403_FORBIDDEN)

        content = request.data.get('content', '').strip()
        if not content:
            return Response({'error': 'content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            member = Member.objects.get(id=request.user.id)
            msg = Message.objects.create(
                conversation_id=conversation_id,
                sender=member,
                content=content,
            )
            Conversation.objects.filter(id=conversation_id).update(updated_at=timezone.now())

        serializer = MessageSerializer(msg, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConversationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, conversation_id):
        updated = ConversationParticipant.objects.filter(
            conversation_id=conversation_id,
            member_id=request.user.id,
        ).update(last_read_at=timezone.now())

        if not updated:
            return Response({'error': 'Not a participant.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'message': 'Marked as read.'})
