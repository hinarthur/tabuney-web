from django.urls import path
from .views import (
    ContactInquiryView,
    ConversationListView,
    ConversationMessageView,
    ConversationMarkReadView,
)

urlpatterns = [
    path('contact/', ContactInquiryView.as_view(), name='messaging-contact'),
    path('conversations/', ConversationListView.as_view(), name='messaging-conversations'),
    path('conversations/<int:conversation_id>/messages/', ConversationMessageView.as_view(), name='messaging-messages'),
    path('conversations/<int:conversation_id>/read/', ConversationMarkReadView.as_view(), name='messaging-mark-read'),
]
