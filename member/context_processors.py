# member/context_processors.py
from django.conf import settings

def google_client_id(request):
    return {
        "SOCIAL_AUTH_GOOGLE_CLIENT_ID": settings.SOCIAL_AUTH_GOOGLE_CLIENT_ID
    }


def beta_mode(request):
    """模板用 {% if beta_mode %} 隱藏付費 UI（見 member/beta.py）。"""
    from member.beta import is_beta
    return {"beta_mode": is_beta()}
