# member/services.py
"""
Google OAuth and Authentication Services
Handle third-party authentication logic separately from views
"""
import os
import time
import requests
from dotenv import load_dotenv
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Member
from translation.models import Tribe

load_dotenv()


class GoogleAuthService:
    """Handle Google OAuth2 token verification and user management"""
    
    GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'
    
    @staticmethod
    def verify_google_token(id_token_str):
        """
        Verify Google OAuth2 ID token
        
        Args:
            id_token_str: Google ID token string
            
        Returns:
            dict: Decoded token info (idinfo)
            
        Raises:
            ValueError: If token verification fails
        """
        try:
            google_client_ids_str = os.environ.get("GOOGLE_CLIENT_IDS")
            if google_client_ids_str:
                google_client_ids = [
                    x.strip() for x in google_client_ids_str.split(",") if x.strip()
                ]
            else:
                google_client_ids = []
            
            idinfo = id_token.verify_oauth2_token(
                id_token_str,
                google_requests.Request(),
                google_client_ids
            )
            return idinfo
        except ValueError as e:
            msg = str(e)
            # Token used too early can happen when server clock is slightly behind.
            # Retry once after a short delay as a pragmatic workaround.
            if 'Token used too early' in msg or 'Used too early' in msg:
                time.sleep(1)
                try:
                    idinfo = id_token.verify_oauth2_token(
                        id_token_str,
                        google_requests.Request(),
                        google_client_ids
                    )
                    return idinfo
                except ValueError:
                    pass
            raise ValueError(f'Invalid id_token: {msg}')
    
    @staticmethod
    def verify_google_access_token(access_token):
        """
        Verify Google OAuth2 access token by fetching user info from Google API
        This is more reliable than id_token when using OAuth2 Token Client
        
        Args:
            access_token: Google access token string
            
        Returns:
            dict: User info from Google (sub, email, name, picture, etc.)
            
        Raises:
            ValueError: If token verification fails
        """
        try:
            response = requests.get(
                GoogleAuthService.GOOGLE_USERINFO_URL,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10
            )
            
            if response.status_code != 200:
                raise ValueError(f'Failed to verify access token: {response.status_code}')
            
            userinfo = response.json()
            
            # Validate required fields
            if not userinfo.get('email'):
                raise ValueError('No email in user info')
            
            # Normalize field names to match id_token format
            return {
                'sub': userinfo.get('sub'),
                'email': userinfo.get('email'),
                'email_verified': userinfo.get('email_verified', False),
                'given_name': userinfo.get('given_name', ''),
                'family_name': userinfo.get('family_name', ''),
                'name': userinfo.get('name', ''),
                'picture': userinfo.get('picture', ''),
            }
            
        except requests.RequestException as e:
            raise ValueError(f'Failed to verify access token: {str(e)}')
    
    @staticmethod
    def get_or_create_user(email, given_name, family_name):
        """
        Get existing user or create new one
        
        Args:
            email: User email
            given_name: User's first name from Google
            family_name: User's last name from Google
            
        Returns:
            tuple: (User object, is_new boolean)
        """
        try:
            user = User.objects.get(email=email)
            user.last_login = timezone.now()
            user.save()
            is_new = False
        except User.DoesNotExist:
            current_time = timezone.now()
            user = User.objects.create(
                username=email,
                email=email,
                first_name=given_name,
                last_name=family_name,
                date_joined=current_time,
                last_login=current_time,
            )
            user.set_unusable_password()
            user.save()
            is_new = True
        
        # Update name fields if provided
        if given_name or family_name:
            user.first_name = given_name
            user.last_name = family_name
            user.save()
        
        return user, is_new
    
    @staticmethod
    def update_member_profile(user, google_id, picture, language_code=None):
        """
        Update or create Member profile with Google data
        
        Args:
            user: Django User object
            google_id: Google account ID
            picture: User avatar URL from Google
            language_code: Optional language preference
            
        Returns:
            Member: Updated Member object
        """
        try:
            member = Member.objects.get(id=user)
        except Member.DoesNotExist:
            # New member - set source to 'web' for Google login
            member = Member.objects.create(id=user, source='web')
        
        member.google_id = google_id
        member.avatar = picture
        
        if language_code:
            try:
                tribe = Tribe.objects.get(language=language_code)
                member.tribe = tribe
            except Tribe.DoesNotExist:
                pass
        
        member.save()
        return member
    
    @staticmethod
    def handle_google_login(id_token_str=None, access_token=None, language_code=None):
        """
        Complete Google login flow
        Supports both id_token and access_token authentication
        
        Args:
            id_token_str: Google ID token (optional)
            access_token: Google access token (optional)
            language_code: Optional language preference
            
        Returns:
            dict: Contains user, member, and is_new flag
            
        Raises:
            ValueError: If token verification fails or no valid token provided
        """
        # Determine which token type to use
        if id_token_str:
            # Verify ID token
            idinfo = GoogleAuthService.verify_google_token(id_token_str)
        elif access_token:
            # Verify access token by fetching user info
            idinfo = GoogleAuthService.verify_google_access_token(access_token)
        else:
            raise ValueError('No valid token provided')
        
        # Extract data
        google_id = idinfo.get('sub')
        email = idinfo.get('email')
        given_name = idinfo.get('given_name', '')
        family_name = idinfo.get('family_name', '')
        picture = idinfo.get('picture', '')
        
        if not email:
            raise ValueError('Email not provided by Google')
        
        # Get or create user
        user, is_new = GoogleAuthService.get_or_create_user(
            email, given_name, family_name
        )
        
        # Update member profile
        member = GoogleAuthService.update_member_profile(
            user, google_id, picture, language_code
        )
        
        return {
            'user': user,
            'member': member,
            'is_new': is_new,
        }