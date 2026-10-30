# member/views.py
import logging
from hmac import compare_digest
from urllib.parse import quote

from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from django.views.generic import View
from .models import EditionUnlock, Member, Tier
from translation.models import Tribe
from .oauth import (
    SESSION_NEXT_KEY,
    SESSION_STATE_KEY,
    SESSION_VERIFIER_KEY,
    build_google_auth_url,
    exchange_code_for_tokens,
    generate_pkce_pair,
    generate_state,
)
from .serializers import MemberSerializer, UserActivitySerializer
from .services import GoogleAuthService
from stats.utils import log_page_visit
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.db import transaction

TRIBE_LANGS = ['de', 'en', 'es', 'fr', 'ja', 'zh']


def establish_web_session(django_request, login_result, refresh):
    """
    登入成功後建立 Django session 並設定介面語言。

    網頁的 code flow 與 App 的 POST 端點都會走這裡，避免兩份會慢慢漂移的複本。
    失敗只記 log 不中斷 —— JWT 已經發出去了，session 建不起來不該讓整個登入失敗。
    """
    member = login_result['member']
    if member.tribe and member.tribe.language and member.tribe.language in TRIBE_LANGS:
        django_request.session['lang'] = member.tribe.language

    try:
        django_login(
            django_request, login_result['user'],
            backend='django.contrib.auth.backends.ModelBackend',
        )
        django_request.session['refresh_token'] = str(refresh)
        django_request.session['access_token'] = str(refresh.access_token)
        django_request.session.save()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Failed to create session: {str(e)}')


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]    
    authentication_classes = []
    
    def post(self, request):
        """
        Handle Google OAuth2 login
        
        Supports two authentication methods:
        
        1. ID Token (from One Tap or redirect flow):
        {
            "id_token": "...",
            "language": "en" (optional)
        }
        
        2. Access Token (from OAuth2 Token Client):
        {
            "access_token": "...",
            "language": "en" (optional)
        }
        """
        id_token_str = request.data.get('id_token')
        access_token = request.data.get('access_token')
        language_code = request.data.get('language')
        
        # Validate that at least one token is provided
        if not id_token_str and not access_token:
            return Response(
                {'error': 'No id_token or access_token provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Use service to handle login (supports both token types)
            login_result = GoogleAuthService.handle_google_login(
                id_token_str=id_token_str,
                access_token=access_token,
                language_code=language_code
            )
            user = login_result['user']
            member = login_result['member']

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)

            # 總是建立 Django session（網頁的 code flow 走的是同一個 helper）
            establish_web_session(request._request, login_result, refresh)

            resp_data = {
                'message': 'Google 登入成功',
                'user': MemberSerializer(member).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
            
            if member.tribe and member.tribe.language and member.tribe.language in TRIBE_LANGS:
                resp_data['tribe_language'] = member.tribe.language
                
            return Response(resp_data)
            
        except ValueError as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Unexpected error during Google login: {str(e)}', exc_info=True)
            return Response(
                {'error': 'An unexpected error occurred during login'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


def _safe_next(request, candidate):
    """
    只接受站內的相對網址，擋掉 open redirect。
    ?next=https://evil.com 這種一律退回首頁。
    """
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return '/'


class GoogleLoginStartView(View):
    """
    網頁登入的起點：GET /api/members/login/google/start/?next=<站內路徑>

    授權網址由後端組而不是瀏覽器，state 與 PKCE 的 code_verifier 才能存進
    Django session 由伺服器驗證。
    """

    def get(self, request):
        state = generate_state()
        verifier, challenge = generate_pkce_pair()

        request.session[SESSION_STATE_KEY] = state
        request.session[SESSION_VERIFIER_KEY] = verifier
        request.session[SESSION_NEXT_KEY] = _safe_next(request, request.GET.get('next'))

        redirect_uri = request.build_absolute_uri(reverse('google-login-callback'))
        return HttpResponseRedirect(
            build_google_auth_url(redirect_uri, state, challenge)
        )


class GoogleLoginCallbackView(View):
    """
    Google 授權後導回這裡：GET /api/members/login/google/callback/?code=…&state=…

    這個路徑已註冊在 Google Console 且被硬編碼過，不能改動；改變的只是
    它現在在後端完成 code 交換，而不是渲染頁面讓前端 JS 去解 URL fragment。
    """

    def get(self, request):
        next_url = request.session.pop(SESSION_NEXT_KEY, '/') or '/'
        expected_state = request.session.pop(SESSION_STATE_KEY, None)
        verifier = request.session.pop(SESSION_VERIFIER_KEY, None)

        logger = logging.getLogger(__name__)

        # 使用者按了取消，或 Google 直接回報錯誤
        error = request.GET.get('error')
        if error:
            logger.info('Google login aborted: %s', error)
            return HttpResponseRedirect(f'/?login_error={quote(error)}')

        code = request.GET.get('code')
        state = request.GET.get('state')

        # state 對不上代表這個 callback 不是我們發起的
        if not code or not expected_state or not state or not compare_digest(state, expected_state):
            logger.warning('Google login callback rejected: state mismatch or missing code')
            return HttpResponseBadRequest('Invalid OAuth state.')

        if not verifier:
            logger.warning('Google login callback rejected: missing PKCE verifier')
            return HttpResponseBadRequest('Invalid OAuth session.')

        redirect_uri = request.build_absolute_uri(reverse('google-login-callback'))

        try:
            tokens = exchange_code_for_tokens(code, verifier, redirect_uri)
            # id_token 的驗證與建帳號沿用既有的 service，不重寫
            login_result = GoogleAuthService.handle_google_login(
                id_token_str=tokens['id_token']
            )
        except ValueError as e:
            logger.error('Google login failed: %s', e)
            return HttpResponseRedirect('/?login_error=exchange_failed')
        except Exception:
            logger.exception('Unexpected error during Google login callback')
            return HttpResponseRedirect('/?login_error=unexpected')

        refresh = RefreshToken.for_user(login_result['user'])
        establish_web_session(request, login_result, refresh)

        return HttpResponseRedirect(next_url)


# ... 其餘的 views 保持不變 ...

class MemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.get(id=request.user.id)
        serializer = MemberSerializer(member)
        return Response(serializer.data)

    def patch(self, request):
        member = Member.objects.get(id=request.user.id)
        data = request.data.copy()

        # 支援以 language 更新 member.tribe
        if 'language' in data:
            lang = data.pop('language')
            if lang in TRIBE_LANGS:
                try:
                    tribe = Tribe.objects.get(language=lang)
                    member.tribe = tribe
                    member.save()
                except Tribe.DoesNotExist:
                    pass

        serializer = MemberSerializer(member, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        
class ActivityTrackView(APIView):
    permission_classes = [AllowAny]
    # 不覆寫 authentication_classes：改用 settings 預設的 SessionAuthentication +
    # JWTAuthentication，App 帶的 Bearer token 才會被驗證，member 才解析得出來。
    # 之前設成 [] 會讓 request.user 永遠是匿名，已登入使用者的事件因此拿不到
    # member、又沒帶 session_id，結果被下面的檢查以 400 打回，等於完全沒記到。

    def post(self, request):
        data = request.data.copy()

        member = None
        if request.user and request.user.is_authenticated:
            try:
                member = Member.objects.get(id=request.user.id)
            except Member.DoesNotExist:
                member = None
                
        if not member:
            if "session_id" not in data or not data["session_id"]:
                return Response(
                    {"detail": "匿名狀態下需提供 session_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        serializer = UserActivitySerializer(data=data)

        if serializer.is_valid():
            serializer.save(member=member)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EditionUnlockPickView(View):
    """用一個免費名額永久解鎖一款 Edition。

    免費名額預設 3 個（tier feature 'edition_unlock'，見 member/features.py），
    用完之後的加購走 commerce.create_edition_unlock_session（US$1 一次性付款）。

    純 POST + redirect，不做 AJAX：唯一的入口是 edition info 分頁上的表單，
    搜尋頁的星星只顯示狀態、不可點。
    """

    def post(self, request):
        from game.models import Edition

        if not request.user.is_authenticated:
            return HttpResponseRedirect(reverse('account:membership'))

        edition_id = (request.POST.get('edition_id') or '').strip()
        edition = Edition.objects.filter(id=edition_id).first() if edition_id else None
        if edition is None:
            return HttpResponseRedirect(reverse('games:search'))

        back = _edition_info_url(edition)
        member = request.user.member

        # 名額計算與寫入必須在同一個交易內，並先鎖住這位會員既有的列：
        # 雙開分頁同時送出時，兩個 request 各自數到 2/3 然後各寫一筆，
        # 名額就被灌成 4。UniqueConstraint 只擋得住重複選同一款。
        with transaction.atomic():
            locked = list(
                EditionUnlock.objects.select_for_update()
                .filter(member=member).values_list('edition_id', 'source')
            )
            if any(eid == edition.id for eid, _ in locked):
                return HttpResponseRedirect(back)  # 已經有了，什麼都不用做

            used = sum(1 for _, src in locked if src == EditionUnlock.Source.FREE)
            quota = member.limit('edition_unlock')
            if quota != -1 and used >= quota:
                messages.error(request, _unlock_msg(request, 'game.unlock.error.quota'))
                return HttpResponseRedirect(back)

            EditionUnlock.objects.create(
                member=member, edition=edition, source=EditionUnlock.Source.FREE,
            )

        member.invalidate_unlocked_cache()
        messages.success(request, _unlock_msg(request, 'game.unlock.success'))
        return HttpResponseRedirect(back)


class EditionUnlockReleaseView(View):
    """退回一個免費名額。

    只有在該 edition **完全沒有已發布流程圖**時才允許——那代表還沒有東西可以
    解鎖，名額等於被白佔。只要有任何一張圖上線，這筆選擇就永久定案。

    付費加購的列一律不可退回。購買前就擋掉了沒有流程圖的 edition，所以付費列
    不該出現在這個狀態；這裡再擋一次是防禦性寫法。
    """

    def post(self, request):
        from game.models import Edition
        from game.selectors import editions_with_published_flowchart

        if not request.user.is_authenticated:
            return HttpResponseRedirect(reverse('account:membership'))

        edition_id = (request.POST.get('edition_id') or '').strip()
        edition = Edition.objects.filter(id=edition_id).first() if edition_id else None
        if edition is None:
            return HttpResponseRedirect(reverse('games:search'))

        back = _edition_info_url(edition)
        member = request.user.member

        unlock = EditionUnlock.objects.filter(member=member, edition=edition).first()
        if unlock is None:
            return HttpResponseRedirect(back)

        if unlock.source != EditionUnlock.Source.FREE:
            messages.error(request, _unlock_msg(request, 'game.unlock.error.locked_in'))
            return HttpResponseRedirect(back)

        if editions_with_published_flowchart([edition.id]):
            messages.error(request, _unlock_msg(request, 'game.unlock.error.locked_in'))
            return HttpResponseRedirect(back)

        unlock.delete()
        member.invalidate_unlocked_cache()
        messages.success(request, _unlock_msg(request, 'game.unlock.released'))
        return HttpResponseRedirect(back)


def _edition_info_url(edition):
    return f"{edition.get_absolute_url()}info/"


def _unlock_msg(request, key):
    """翻譯表查不到就退回 key 本身，與 {% t %} 的行為一致。"""
    from translation.models import Translation
    try:
        tribe = Tribe.objects.get(language=getattr(request, 'lang', 'en'))
        return Translation.objects.get(tribe=tribe, key=key).value
    except Exception:
        return key


class MembershipSuccessView(View):
    def get(self, request):
        return render(request, 'membership_success.html')


class MembershipCancelView(View):
    def get(self, request):
        return render(request, 'membership_cancel.html')
    
class MembershipView(View):
    def get(self, request):
        log_page_visit(request, 'membership')
        # Default tier if not authenticated or not set
        current_tier = 'free'
        subscription = None
        my_unlocks = []
        unlock_free_used = 0
        unlock_free_quota = 0

        if request.user.is_authenticated:
            try:
                member_instance = Member.objects.get(id=request.user.id)
                subscription = getattr(member_instance, 'subscription', None)
                current_tier = member_instance.tier_code
                # 權益不可逆，使用者得查得到自己用掉了哪幾款
                my_unlocks = list(
                    member_instance.edition_unlocks
                    .select_related('edition').order_by('created_at')
                )
                unlock_free_used, unlock_free_quota = member_instance.free_unlock_usage()
            except Member.DoesNotExist:
                pass

        context = {
            'current_tier': current_tier,
            'subscription': subscription,
            'my_unlocks': my_unlocks,
            'unlock_free_used': unlock_free_used,
            'unlock_free_quota': unlock_free_quota,
            # 與 edition info 分頁印同一組數字，見 settings 的註解
            'edition_access_list_price': settings.EDITION_ACCESS_LIST_PRICE,
            'edition_access_current_price': settings.EDITION_ACCESS_CURRENT_PRICE,
        }
        return render(request, 'membership.html', context)
    
    
class LogoutView(APIView):
    """
    处理用户登出
    POST /api/members/logout/
    """
    permission_classes = []
    
    def post(self, request):
        django_logout(request)
        
        response = Response({
            'success': True,
            'message': 'Logged out successfully'
        }, status=status.HTTP_200_OK)
        
        response.delete_cookie('sessionid')
        response.delete_cookie('csrftoken')
        response.delete_cookie('access_token')
        response.delete_cookie('refresh_token')
        
        return response