"""
Google OAuth 2.0 authorization code flow + PKCE。

為什麼是 code flow 而不是 implicit flow（response_type=token）：
  * implicit flow 自 2019 年起被 Google 標為不建議使用，新建的 OAuth client 已不能用
  * token 會出現在網址列與瀏覽紀錄裡
  * code 只能用一次，且綁定 code_verifier，攔截到也無法重放

授權網址由後端組（不是瀏覽器），這樣 state 與 code_verifier 才能放進 Django session
讓伺服器自己驗證 —— 放在 sessionStorage 的話後端讀不到，等於沒有 CSRF 防護。
"""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE = "openid email profile"

# session 的鍵名，start 與 callback 兩個 view 共用
SESSION_STATE_KEY = "google_oauth_state"
SESSION_VERIFIER_KEY = "google_oauth_verifier"
SESSION_NEXT_KEY = "google_oauth_next"


def generate_state():
    """防 CSRF 用的一次性亂數。"""
    return secrets.token_urlsafe(32)


def generate_pkce_pair():
    """
    產生 PKCE 的 (code_verifier, code_challenge)。

    challenge = base64url(sha256(verifier))，去掉 '=' padding —— RFC 7636 規定
    不能有 padding，多留會被 Google 判為 invalid_grant。
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_google_auth_url(redirect_uri, state, code_challenge):
    """組出要把使用者導過去的 Google 授權網址。"""
    params = {
        "client_id": settings.SOCIAL_AUTH_GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code, code_verifier, redirect_uri):
    """
    拿 authorization code 跟 Google 換 token。

    這是伺服器端行為，會帶上 client_secret，所以正式環境的
    SOCIAL_AUTH_GOOGLE_SECRET 一定要有值。

    回傳 Google 的 token 回應（含 id_token / access_token）。失敗時丟 ValueError。
    """
    if not settings.SOCIAL_AUTH_GOOGLE_SECRET:
        raise ValueError("SOCIAL_AUTH_GOOGLE_SECRET is not configured")

    try:
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.SOCIAL_AUTH_GOOGLE_CLIENT_ID,
                "client_secret": settings.SOCIAL_AUTH_GOOGLE_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise ValueError(f"Failed to reach Google token endpoint: {exc}") from exc

    if response.status_code != 200:
        # Google 會回 {"error": "invalid_grant", "error_description": "..."}
        try:
            detail = response.json().get("error_description") or response.json().get("error")
        except ValueError:
            detail = response.text[:200]
        raise ValueError(f"Google token exchange failed: {detail}")

    payload = response.json()
    if not payload.get("id_token"):
        raise ValueError("Google token response did not include an id_token")
    return payload
