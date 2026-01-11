"""Authentication module for Google OAuth2 integration."""

# Optional imports - allow tests to run without Google OAuth dependencies
try:
    from .google_oauth2 import GoogleOAuth2Handler
    from .oauth2_middleware import OAuth2Middleware, get_current_user
    __all__ = ["GoogleOAuth2Handler", "OAuth2Middleware", "get_current_user"]
except ImportError:
    # If Google OAuth dependencies are not installed, export None or stub classes
    # This allows tests to run without requiring google-auth packages
    GoogleOAuth2Handler = None
    OAuth2Middleware = None
    get_current_user = None
    __all__ = ["GoogleOAuth2Handler", "OAuth2Middleware", "get_current_user"]

