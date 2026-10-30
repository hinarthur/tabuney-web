from django.urls import path
from django.views.generic import RedirectView
from game.legacy_views import LegacyEditionRedirect
from game.views import ChatView, RulebookQAView, RulebookFlowchartView, RulebookFlowchartAdjustView, RulebookScriptView, MessageFeedbackView, ClearChatView, InteractionAPIView, CollectionAPIView
from game.sync_views import sync_game_data, sync_media, sync_qdrant

urlpatterns = [
    # ─── 舊的公開網址：已搬到 /games/，一律 301 ───
    # 新 App 的等價端點是 GET /api/v1/games/ 與 /api/v1/games/<uuid>/。
    path("search/", RedirectView.as_view(pattern_name="games:search", permanent=True,
                                         query_string=True), name="game-search"),
    path("edition/<uuid:pk>/", LegacyEditionRedirect.as_view(), name="edition-detail"),
    # RAG QA
    path(
        "rulebooks/<uuid:rulebook_id>/qa/",
        RulebookQAView.as_view(),
        name="rulebook-qa"
    ),

    # RAG Flowchart
    path(
        "rulebooks/<uuid:rulebook_id>/flowchart/",
        RulebookFlowchartView.as_view(),
        name="rulebook-flowchart"
    ),
    path(
        "rulebooks/<uuid:rulebook_id>/flowchart/adjust/",
        RulebookFlowchartAdjustView.as_view(),
        name="rulebook-flowchart-adjust"
    ),

    # Game master 講稿（只讀，僅出 approved）
    path(
        "rulebooks/<uuid:rulebook_id>/script/",
        RulebookScriptView.as_view(),
        name="rulebook-script"
    ),

    # Chat API
    path(
        "editions/<uuid:edition_id>/chat/",
        ChatView.as_view(),
        name="chat-api",
    ),

    # Message Feedback
    path(
        "messages/<message_id>/feedback/",
        MessageFeedbackView.as_view(),
        name="message-feedback",
    ),

    # Clear Chat History
    path(
        "editions/<uuid:edition_id>/chat/clear/",
        ClearChatView.as_view(),
        name="clear-chat",
    ),

    # User Interaction (collection status + rating) for mobile app
    path(
        "editions/<uuid:edition_id>/interaction/",
        InteractionAPIView.as_view(),
        name="edition-interaction-api",
    ),

    # Collection API (for mobile app)
    path(
        "collection/",
        CollectionAPIView.as_view(),
        name="collection-api",
    ),

    # ─── Sync API (VPS receiver endpoints) ───
    path("sync-data/", sync_game_data, name="sync-game-data"),
    path("sync-media/", sync_media, name="sync-media"),
    path("sync-qdrant/<str:collection_name>/", sync_qdrant, name="sync-qdrant"),
]