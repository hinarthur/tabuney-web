# translation/urls.py

from django.urls import path
from .views import TranslationListView, TribeListView, GetLanguageView, SyncTranslationView

urlpatterns = [
    path('get_text/', TranslationListView.as_view()),
    path('tribes/', TribeListView.as_view()),
    path('get-language/', GetLanguageView.as_view(), name='get-language'),
    path('sync-translation/', SyncTranslationView.as_view()),
]