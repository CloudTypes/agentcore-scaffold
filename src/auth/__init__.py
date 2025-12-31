"""Authentication module for Google OAuth2 integration."""

from .google_oauth2 import GoogleOAuth2Handler
from .oauth2_middleware import OAuth2Middleware, get_current_user

__all__ = ["GoogleOAuth2Handler", "OAuth2Middleware", "get_current_user"]

