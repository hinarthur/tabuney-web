# member/context_processors.py
from django.conf import settings

def google_client_id(request):
    return {
        "SOCIAL_AUTH_GOOGLE_CLIENT_ID": settings.SOCIAL_AUTH_GOOGLE_CLIENT_ID
    }
