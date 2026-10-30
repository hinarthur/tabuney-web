from django.urls import path
from django.contrib.staticfiles.storage import staticfiles_storage
from django.views.generic.base import RedirectView
from .views import TableJourneyView, DashboardView

urlpatterns = [
    path('', TableJourneyView.as_view(), name='tablejourney'),
    path('favicon.ico', RedirectView.as_view(url=staticfiles_storage.url('tablejourney/favico/favicon.ico'))),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
]
