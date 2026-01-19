"""Google OAuth2 authentication handler.

This module provides a complete OAuth2 authentication flow for Google accounts,
including authorization URL generation, callback handling, and JWT token creation
for session management.

Example:
    Basic usage::

        handler = GoogleOAuth2Handler()
        auth_url, state = handler.get_authorization_url()
        # Redirect user to auth_url
        # After callback, exchange code for token:
        user_info = await handler.handle_callback(code, state)
        jwt_token = user_info["token"]
"""

import os
import logging
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import jwt

# Optional Google OAuth imports - handle missing dependencies gracefully
try:
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token
    from google_auth_oauthlib.flow import Flow

    GOOGLE_OAUTH_AVAILABLE = True
except ImportError:
    # Google OAuth dependencies not installed (e.g., in test environment)
    GOOGLE_OAUTH_AVAILABLE = False
    Request = None
    id_token = None
    Flow = None

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class GoogleOAuth2Handler:
    """Handles Google OAuth2 authentication flow.

    This class manages the complete OAuth2 authentication lifecycle:
    - Generating authorization URLs for user consent
    - Handling OAuth2 callbacks and exchanging authorization codes for tokens
    - Verifying Google ID tokens
    - Creating and verifying JWT tokens for session management
    - Enforcing domain restrictions for Google Workspace organizations

    The handler requires the following environment variables:
    - GOOGLE_CLIENT_ID: Google OAuth2 client ID
    - GOOGLE_CLIENT_SECRET: Google OAuth2 client secret
    - JWT_SECRET_KEY: Secret key for signing JWT tokens
    - GOOGLE_REDIRECT_URI: OAuth2 redirect URI (optional, defaults to localhost)
    - GOOGLE_WORKSPACE_DOMAIN: Domain restriction for Google Workspace (optional)
    - JWT_EXPIRATION_MINUTES: JWT token expiration time in minutes (optional, defaults to 60)
    - JWT_ALGORITHM: JWT signing algorithm (optional, defaults to HS256)

    Raises:
        ImportError: If Google OAuth2 dependencies are not installed
        ValueError: If required environment variables are missing
    """

    # OAuth2 endpoints
    AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
    TOKEN_URI = "https://oauth2.googleapis.com/token"

    # OAuth2 scopes
    SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"]

    def __init__(self):
        """Initialize OAuth2 handler with configuration from environment variables.

        Loads all required OAuth2 and JWT configuration from environment variables
        and validates that all required settings are present.

        Raises:
            ImportError: If Google OAuth2 dependencies are not installed.
                Install with: pip install google-auth google-auth-oauthlib
            ValueError: If required environment variables are missing:
                - GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (both required)
                - JWT_SECRET_KEY (required)
        """
        if not GOOGLE_OAUTH_AVAILABLE:
            raise ImportError(
                "Google OAuth2 dependencies are not installed. "
                "Please install them with: pip install google-auth google-auth-oauthlib"
            )

        self.client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/api/auth/callback")
        self.workspace_domain = os.getenv("GOOGLE_WORKSPACE_DOMAIN")
        self.jwt_secret = os.getenv("JWT_SECRET_KEY")
        self.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.jwt_expiration_minutes = int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))

        if not self.client_id or not self.client_secret:
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")

        if not self.jwt_secret:
            raise ValueError("JWT_SECRET_KEY must be set")

        # Validate JWT secret has minimum length for security
        if len(self.jwt_secret) < 32:
            logger.warning(
                "JWT_SECRET_KEY is shorter than 32 characters. " "Consider using a longer secret for better security."
            )

    def _create_flow(self) -> Flow:
        """Create a Google OAuth2 Flow instance with configured client settings.

        This helper method eliminates code duplication by centralizing the Flow
        creation logic used by both get_authorization_url() and handle_callback().

        Returns:
            Flow: Configured Google OAuth2 Flow instance

        Raises:
            ValueError: If Flow creation fails due to invalid configuration
        """
        return Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": self.AUTH_URI,
                    "token_uri": self.TOKEN_URI,
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri,
        )

    def get_authorization_url(self, state: Optional[str] = None) -> tuple[str, str]:
        """Generate Google OAuth2 authorization URL for user consent.

        Creates an authorization URL that the user should be redirected to for
        Google OAuth2 authentication. The URL includes all necessary parameters
        for the OAuth2 flow, including scopes and state for CSRF protection.

        Args:
            state: Optional state parameter for CSRF protection. If not provided,
                a secure random state token will be generated automatically.
                The state should be stored (e.g., in session) and validated
                during the callback to prevent CSRF attacks.

        Returns:
            tuple[str, str]: A tuple containing:
                - authorization_url (str): The Google OAuth2 authorization URL
                  to redirect the user to
                - state (str): The state parameter (either provided or generated)
                  that should be validated during callback

        Example:
            >>> handler = GoogleOAuth2Handler()
            >>> auth_url, state = handler.get_authorization_url()
            >>> # Store state in session
            >>> # Redirect user to auth_url
        """
        if state is None:
            state = secrets.token_urlsafe(32)

        flow = self._create_flow()

        authorization_url, _ = flow.authorization_url(
            access_type="offline", include_granted_scopes="true", state=state, prompt="consent"
        )

        return authorization_url, state

    async def handle_callback(self, code: str, state: Optional[str] = None) -> Dict[str, Any]:
        """Handle OAuth2 callback and exchange authorization code for tokens.

        This method processes the OAuth2 callback from Google, exchanges the
        authorization code for access/ID tokens, verifies the ID token, extracts
        user information, and creates a JWT token for session management.

        Note: This method is marked as async for API compatibility and to support
        potential future async operations (e.g., async token verification or
        database lookups). Currently, all operations are synchronous.

        Args:
            code: Authorization code received from Google OAuth2 callback.
                This is a one-time use code that must be exchanged for tokens
                immediately.
            state: Optional state parameter received from the callback. This should
                match the state value provided during get_authorization_url() for
                CSRF protection. Note: This method accepts the state parameter
                but does not validate it - validation should be performed by the
                caller using the state stored during authorization URL generation.

        Returns:
            Dict[str, Any]: A dictionary containing:
                - email (str): User's email address (required)
                - name (str, optional): User's full name
                - picture (str, optional): URL to user's profile picture
                - domain (str, optional): Google Workspace domain (hd claim)
                - token (str): JWT token for session management

        Raises:
            ValueError: If any of the following occur:
                - Invalid or expired authorization code
                - ID token verification fails
                - Required email field is missing from ID token
                - Domain restriction is configured and user's domain doesn't match
            Exception: If token exchange or ID token verification fails

        Example:
            >>> handler = GoogleOAuth2Handler()
            >>> # After user returns from Google OAuth2 consent page
            >>> user_info = await handler.handle_callback(code, stored_state)
            >>> jwt_token = user_info["token"]
            >>> user_email = user_info["email"]
        """
        flow = self._create_flow()

        # Exchange code for tokens
        try:
            flow.fetch_token(code=code)
        except Exception as e:
            logger.error(f"Failed to exchange authorization code for tokens: {e}")
            raise ValueError(f"Invalid authorization code: {str(e)}")

        # Get ID token
        credentials = flow.credentials
        if not credentials or not credentials.id_token:
            logger.error("No ID token received from token exchange")
            raise ValueError("No ID token received from Google")

        id_token_str = credentials.id_token

        # Verify ID token
        try:
            idinfo = id_token.verify_oauth2_token(id_token_str, Request(), self.client_id)
        except ValueError as e:
            logger.error(f"Invalid ID token: {e}")
            raise ValueError(f"Invalid ID token: {str(e)}")

        # Extract user information
        email = idinfo.get("email")
        name = idinfo.get("name")
        picture = idinfo.get("picture")
        hosted_domain = idinfo.get("hd")  # Google Workspace domain

        # Validate required fields
        if not email:
            logger.error("Email field missing from ID token")
            raise ValueError("Email is required but missing from ID token")

        # Verify domain restriction if configured
        if self.workspace_domain:
            if hosted_domain != self.workspace_domain:
                logger.warning(
                    f"Domain mismatch: user domain '{hosted_domain}' "
                    f"does not match required domain '{self.workspace_domain}'"
                )
                raise ValueError(
                    f"Access restricted to {self.workspace_domain} domain. " f"User domain: {hosted_domain or 'not provided'}"
                )

        # Create JWT token
        jwt_token = self._create_jwt_token(email=email, name=name, picture=picture, domain=hosted_domain)

        logger.info(f"Successfully authenticated user: {email}")

        return {"email": email, "name": name, "picture": picture, "domain": hosted_domain, "token": jwt_token}

    def _create_jwt_token(
        self, email: str, name: Optional[str] = None, picture: Optional[str] = None, domain: Optional[str] = None
    ) -> str:
        """Create JWT token for user session management.

        Generates a JSON Web Token containing user information and expiration
        time. The token is signed using the configured JWT secret and algorithm.

        Args:
            email: User's email address (required). This is the primary identifier
                and is typically used as the actor_id in the application.
            name: User's full name (optional). Retrieved from Google profile.
            picture: URL to user's profile picture (optional). Retrieved from
                Google profile.
            domain: Google Workspace domain (optional). The 'hd' claim from the
                ID token, indicating the user's organization domain.

        Returns:
            str: Encoded JWT token string that can be used for authentication
                in subsequent requests. The token includes:
                - email: User's email address
                - name: User's name (if available)
                - picture: Profile picture URL (if available)
                - domain: Workspace domain (if available)
                - iat: Issued at timestamp (UTC)
                - exp: Expiration timestamp (UTC)

        Raises:
            Exception: If JWT encoding fails (e.g., invalid secret or algorithm)
        """
        now = datetime.utcnow()
        payload = {
            "email": email,
            "name": name,
            "picture": picture,
            "domain": domain,
            "iat": now,
            "exp": now + timedelta(minutes=self.jwt_expiration_minutes),
        }

        try:
            token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
            return token
        except Exception as e:
            logger.error(f"Failed to encode JWT token: {e}")
            raise ValueError(f"Failed to create JWT token: {str(e)}")

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token.

        Validates the JWT token signature, expiration, and other claims.
        Returns the decoded payload if the token is valid.

        Args:
            token: JWT token string to verify. This should be the token
                received from handle_callback() or stored from a previous
                authentication session.

        Returns:
            Dict[str, Any]: Decoded token payload containing:
                - email (str): User's email address
                - name (str, optional): User's name
                - picture (str, optional): Profile picture URL
                - domain (str, optional): Workspace domain
                - iat (int): Issued at timestamp
                - exp (int): Expiration timestamp
                - Other claims as included in the original token

        Raises:
            ValueError: If the token is invalid, expired, or verification fails.
                Specific error messages include:
                - "Token has expired" for expired tokens
                - "Invalid token: <details>" for other validation failures

        Example:
            >>> handler = GoogleOAuth2Handler()
            >>> try:
            ...     payload = handler.verify_token(jwt_token)
            ...     user_email = payload["email"]
            ... except ValueError as e:
            ...     # Handle invalid/expired token
        """
        if not token:
            raise ValueError("Token cannot be empty")

        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Attempted to verify expired JWT token")
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            raise ValueError(f"Invalid token: {str(e)}")
