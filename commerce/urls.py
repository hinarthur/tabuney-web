from django.urls import path
from . import views

app_name = 'commerce'

urlpatterns = [
    path('create-checkout-session/', views.create_checkout_session, name='create-checkout-session'),
    path('unlock-edition/', views.create_edition_unlock_session, name='create-edition-unlock-session'),
    path('webhook/', views.stripe_webhook, name='stripe-webhook'),
    path('cancel-subscription/', views.cancel_subscription, name='cancel-subscription'),
    path('resume-subscription/', views.resume_subscription, name='resume-subscription'),
]
