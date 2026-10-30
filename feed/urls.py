# feed/urls.py
from django.urls import path, include
from .views import (
    FeedListView, FeedFilterConfigView, SaveFeedlistLangView,
    FetchRssView, ResetRssTasksView, AddRssView, WorkViewSet,
    SaveWorkNoLabelView, FeedBookmarkView, WorkLabelViewSet, SavedWorkViewSet,
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'article', WorkViewSet, basename='article')
router.register(r'work-label', WorkLabelViewSet, basename='work-label')
router.register(r'savedwork', SavedWorkViewSet, basename='savedwork')

urlpatterns = [
    path('list/', FeedListView.as_view(), name='feed-list'),
    path('filter-config/', FeedFilterConfigView.as_view(), name='feed-filter-config'),
    path('save-feedlist-lang/', SaveFeedlistLangView.as_view(), name='save-feedlist-lang'),
    path('fetch-rss/', FetchRssView.as_view(), name='fetch_rss'),
    path('reset_rss_tasks/', ResetRssTasksView.as_view(), name='reset_rss_tasks'),
    path('', include(router.urls)),
    # path('rss-stats/', getRssStats.as_view(), name='rss-stats'),
    path('add_rss/', AddRssView.as_view(), name='add_rss'),
    path('save_work/', SaveWorkNoLabelView.as_view(), name='save_work'),
    path('bookmarks/', FeedBookmarkView.as_view(), name='bookmarks'),
]
